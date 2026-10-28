"""HTTP routes: upload form and audit endpoint.

Flow:
1. GET /  -> render the upload form (index.html).
2. POST /audit -> validate the upload, write to a temp file, run the existing
   profiling engine, render results.html. Temp file is cleaned up in a
   ``finally`` block on every path.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from fastapi import Request, UploadFile, File
from fastapi.templating import Jinja2Templates

from web.upload import (
    cleanup_temp,
    preflight_csv,
    receive_upload,
    UploadError,
)
from dataguard.profile import load_csv, profile_rows
from dataguard.errors import (
    DataGuardError,
    InvalidPathError,
    EncodingError,
    EmptyFileError,
    MalformedCSVError,
)

from web.app import MAX_ROWS, MAX_COLUMNS, AUDIT_TIMEOUT_SECONDS


def setup(app, templates: Jinja2Templates) -> None:
    """Register routes on the FastAPI app."""

    @app.get("/")
    async def index(request: Request):
        """Render the CSV upload form."""
        return templates.TemplateResponse(request, "index.html", {})

    @app.post("/audit")
    async def audit(request: Request, file: UploadFile = File(None)):
        """Validate, profile, and render the audit results for one CSV."""
        if file is None or not file.filename:
            raise UploadError("Please select a CSV file to upload.")
        temp_path: Path | None = None
        try:
            # 1. Receive + size-limit the upload (size enforced during receipt).
            temp_path, stem = await receive_upload(file)

            # 2. Preflight the CSV with a bounded reader so row/column limits
            #    are enforced BEFORE load_csv() reads the whole file into
            #    memory. If preflight rejects, load_csv() is never called.
            preflight_csv(str(temp_path), max_columns=MAX_COLUMNS, max_rows=MAX_ROWS)

            # 3. Load the CSV via the existing engine (requires a filesystem path).
            try:
                rows = load_csv(str(temp_path))
            except (InvalidPathError, EncodingError, EmptyFileError) as exc:
                raise UploadError(str(exc)) from exc

            # 4. Run profiling with a best-effort wall-clock timeout. Each audit
            #    gets its own worker thread so a hung worker never blocks
            #    subsequent requests: every request uses a fresh executor, and on
            #    timeout the executor is abandoned with shutdown(wait=False). The
            #    daemon worker may keep running in the background but cannot block
            #    new audits. future.result(timeout=) bounds how long the REQUEST
            #    waits, but it does NOT interrupt the worker thread (Python
            #    threads cannot be killed). profile_rows() operates on the
            #    in-memory `rows` list, not the temp file, so deleting the temp
            #    file in ``finally`` is safe even if the worker is still running.
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                future = pool.submit(profile_rows, rows)
                result = future.result(timeout=AUDIT_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                raise UploadError(
                    f"The audit took too long to complete "
                    f"> {AUDIT_TIMEOUT_SECONDS}s. Try a smaller file. "
                    "(Timeout is best-effort; the worker thread is not "
                    "interrupted and may keep running in the background.)"
                ) from None
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

            # Attach the sanitized input filename so reports never leak server
            # paths or the raw user filename.
            result.path = stem
            result.encoding = "utf-8-sig"

            # 5. Build the view model and render results.
            view_model = _build_view_model(result, stem)
            return templates.TemplateResponse(
                request,
                "results.html",
                {"vm": view_model},
            )
        except UploadError:
            raise
        except DataGuardError as exc:
            raise UploadError(str(exc)) from exc
        except Exception:  # noqa: BLE001 - never leak tracebacks to the client
            raise UploadError("An unexpected error occurred. Please try again.")
        finally:
            cleanup_temp(temp_path)


def _build_view_model(result, stem: str) -> dict:
    """Convert a :class:`dataguard.profile.ProfileResult` into a view model.

    Only public report fields are used. ``non_missing`` (internal, not
    serialised) is never exposed. CSV-derived values are passed to the template
    unchanged; Jinja2 auto-escapes them on render.
    """
    findings = []

    for issue in result.dataset_issues:
        findings.append(
            {
                "type": "dataset",
                "severity": "warning",
                "context": "",
                "count": 0,
                "explanation": issue,
                "remediation": "Review the affected rows and columns in your CSV.",
            }
        )

    for col in result.columns:
        if col.missing_count:
            findings.append(
                {
                    "type": "missing_values",
                    "severity": "warning",
                    "context": f"Column '{col.name}' (index {col.index})",
                    "count": col.missing_count,
                    "explanation": (
                        f"{col.missing_count} missing cell(s) "
                        f"({col.missing_pct:.1f}%)."
                    ),
                    "remediation": "Fill in missing values or exclude affected rows.",
                }
            )
        if col.dtype == "mixed":
            findings.append(
                {
                    "type": "mixed_type",
                    "severity": "warning",
                    "context": f"Column '{col.name}' (index {col.index})",
                    "count": len(col.suspicious),
                    "explanation": "Mixed or ambiguous types detected.",
                    "remediation": "Standardize values to a single type.",
                }
            )
        if col.is_constant:
            findings.append(
                {
                    "type": "constant_column",
                    "severity": "warning",
                    "context": f"Column '{col.name}' (index {col.index})",
                    "count": 1,
                    "explanation": "Column has the same value in every row.",
                    "remediation": "Consider whether this column adds useful information.",
                }
            )
        if col.is_duplicate:
            findings.append(
                {
                    "type": "duplicate_column",
                    "severity": "warning",
                    "context": f"Column '{col.name}' (index {col.index})",
                    "count": 1,
                    "explanation": "Duplicate column header.",
                    "remediation": "Remove or rename the duplicate column.",
                }
            )

    if result.duplicate_row_count:
        findings.append(
            {
                "type": "duplicate_rows",
                "severity": "warning",
                "context": "Dataset",
                "count": result.duplicate_row_count,
                "explanation": (
                    f"{result.duplicate_row_count} row(s) are exact duplicates "
                    "of an earlier row."
                ),
                "remediation": "Remove exact duplicate rows.",
            }
        )
    if result.ragged_rows:
        findings.append(
            {
                "type": "ragged_rows",
                "severity": "warning",
                "context": "Dataset",
                "count": result.ragged_rows,
                "explanation": (
                    f"{result.ragged_rows} row(s) have a different number of "
                    f"fields than the header ({result.column_count})."
                ),
                "remediation": "Fix rows with missing or extra fields.",
            }
        )
    if result.all_missing_columns:
        findings.append(
            {
                "type": "all_missing_columns",
                "severity": "warning",
                "context": "Dataset",
                "count": len(result.all_missing_columns),
                "explanation": (
                    "All-missing column(s): "
                    + ", ".join(result.all_missing_columns)
                ),
                "remediation": "Remove columns that contain no data.",
            }
        )

    return {
        "input_file": stem,
        "row_count": result.row_count,
        "column_count": result.column_count,
        "total_missing": result.total_missing,
        "duplicate_row_count": result.duplicate_row_count,
        "duplicate_column_count": len(result.duplicate_columns),
        "constant_column_count": len(result.constant_columns),
        "all_missing_column_count": len(result.all_missing_columns),
        "ragged_rows": result.ragged_rows,
        "mixed_type_columns": sum(1 for c in result.columns if c.dtype == "mixed"),
        "findings": findings,
        "columns": result.columns,
    }
