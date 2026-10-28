"""Secure CSV upload handling.

Responsibilities:
* Validate the uploaded file has a ``.csv`` extension.
* Receive the upload in bounded chunks, enforcing a maximum size while data is
  being received (before the profiling engine ever sees it).
* Preflight the temporary CSV with a bounded reader so row/column limits are
  enforced before the engine loads the whole file into memory.
* Write to a randomized temporary file inside a controlled temp directory.
* Provide best-effort cleanup of temporary files.

The original filename and MIME type are treated as untrusted. Only the sanitized
stem is ever used in user-facing messages.
"""

from __future__ import annotations

import csv as _csv
import os
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import UploadFile

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MiB
UPLOAD_CHUNK = 64 * 1024  # 64 KiB reads

# Maximum field size tolerated during preflight. A single field larger than
# this raises ``csv.Error`` and is rejected with a user-friendly message.
MAX_FIELD_SIZE = 1_000_000  # 1 MiB

# ``csv.field_size_limit()`` is process-global. This lock serialises the
# save/change/use/restore sequence so concurrent preflights cannot observe or
# clobber each other's limit. It does not share temp paths or audit results.
_FIELD_SIZE_LOCK = threading.Lock()


class UploadError(Exception):
    """Base class for upload-related errors."""


class FileTooLargeError(UploadError):
    """The uploaded file exceeds the maximum size."""


class InvalidExtensionError(UploadError):
    """The uploaded file does not have a .csv extension."""


class EmptyFileError(UploadError):
    """The uploaded file is empty."""



def _sanitize_stem(filename: str | None) -> str:
    """Return a safe filename stem with no path separators or traversal.

    Path separators are stripped, ``..`` is rejected, and the result is reduced
    to alphanumerics, dashes, underscores and spaces. Falls back to ``upload``.
    """
    if not filename:
        return "upload"
    base = os.path.basename(filename)
    base = base.replace("/", "").replace("\\", "")
    if base in ("", ".", ".."):
        return "upload"
    stem = os.path.splitext(base)[0] or "upload"
    safe = "".join(c for c in stem if c.isalnum() or c in ("-", "_", " ")).strip()
    return safe or "upload"


def validate_extension(filename: str | None) -> None:
    """Reject files without a ``.csv`` extension."""
    if not filename or not filename.lower().endswith(".csv"):
        raise InvalidExtensionError(
            "Please upload a CSV file (.csv extension)."
        )


async def receive_upload(upload: UploadFile) -> tuple[Path, str]:
    """Receive an upload with a size limit, writing to a randomized temp file.

    Returns ``(temp_path, sanitized_stem)``.
    Raises ``UploadError`` subclasses on rejection. Temporary files are removed
    before re-raising so nothing is left behind on validation failure.
    """
    temp_path: Path | None = None
    try:
        validate_extension(upload.filename)

        temp_dir = Path(tempfile.gettempdir()) / "dataguard-uploads"
        temp_dir.mkdir(mode=0o700, exist_ok=True)

        stem = _sanitize_stem(upload.filename)
        temp_name = f"{uuid.uuid4().hex}_{stem}.csv"
        temp_path = temp_dir / temp_name

        size = 0
        with open(temp_path, "wb") as out:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    raise FileTooLargeError(
                        f"File is too large. Maximum size is "
                        f"{MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                    )
                out.write(chunk)

        if size == 0:
            raise EmptyFileError("The uploaded file is empty.")

        return temp_path, stem
    except UploadError:
        cleanup_temp(temp_path)
        raise


def preflight_csv(
    path: str | Path,
    max_columns: int = 1_000,
    max_rows: int = 100_000,
) -> None:
    """Bounded pre-flight read of the temporary CSV before engine load.

    ``load_csv()`` requires a filesystem path and reads the entire file into
    memory via ``list(csv.reader(handle))``. It cannot cap rows or columns
    mid-stream without engine changes, so this preflight pass enforces the
    limits *before* the engine is invoked.

    Checks performed:
    * The file is decodable as UTF-8 (with optional BOM).
    * The header row exists and does not exceed ``max_columns`` fields.
    * Each data row does not exceed ``max_columns`` fields (an unexpectedly
      wide row cannot bypass the column limit).
    * The number of data rows does not exceed ``max_rows``.
    * No single field exceeds ``MAX_FIELD_SIZE`` bytes.

    The file is closed before returning so ``load_csv()`` can reopen it
    independently. Nothing is returned on success; an ``UploadError`` subclass
    is raised on the first violation, and the caller is responsible for
    cleaning up the temp file.

    Limitations
    -----------
    * ``csv.field_size_limit()`` is process-global. It is saved and restored
      around this call, but concurrent preflights could briefly observe each
      other's limit. It does not share temp paths or audit results.
    * This preflight does not eliminate every memory/CPU risk. A file within
      all limits can still consume time in ``profile_rows()`` (bounded only by
      the best-effort wall-clock timeout in the route handler).
    """

    with _FIELD_SIZE_LOCK:
        saved_limit = _csv.field_size_limit(MAX_FIELD_SIZE)
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = _csv.reader(handle)
                try:
                    header = next(reader, None)
                except _csv.Error as exc:
                    raise UploadError(
                        f"Malformed CSV: could not parse header: {exc}"
                    ) from exc

                if header is None:
                    raise EmptyFileError("The file is empty or has no header row.")

                column_count = len(header)
                if column_count > max_columns:
                    raise UploadError(
                        f"File has too many columns ({column_count}). "
                        f"Maximum is {max_columns}."
                    )

                data_rows = 0
                try:
                    for row in reader:
                        # Skip fully blank lines, mirroring load_csv() which drops them.
                        if not row:
                            continue
                        data_rows += 1
                        if data_rows > max_rows:
                            raise UploadError(
                                f"File has too many rows ({data_rows}). "
                                f"Maximum is {max_rows}."
                            )
                        if len(row) > max_columns:
                            raise UploadError(
                                f"Row {data_rows} has {len(row)} fields, exceeding "
                                f"the maximum of {max_columns} columns."
                            )
                except _csv.Error as exc:
                    raise UploadError(f"Malformed CSV: could not parse rows: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise UploadError(
                "Could not read the file with encoding UTF-8. "
                "Please save the CSV as UTF-8 and try again."
            ) from exc
        finally:
            _csv.field_size_limit(saved_limit)


def cleanup_temp(path: Path | None) -> None:
    """Best-effort removal of a temporary file."""
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
