"""Tests for the first web slice: upload form, audit, validation, escaping, cleanup."""

from __future__ import annotations

import csv as _csv
import io
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.app import create_app, MAX_ROWS, MAX_COLUMNS, AUDIT_TIMEOUT_SECONDS
from web.upload import MAX_FIELD_SIZE, MAX_UPLOAD_SIZE, UploadError, preflight_csv
from dataguard.profile import load_csv, profile_rows


@pytest.fixture
def client():
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Startup + form
# ---------------------------------------------------------------------------

def test_upload_form_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Audit a CSV file" in response.text
    assert 'name="file"' in response.text
    assert 'accept=".csv"' in response.text


def test_form_has_accessible_label(client):
    response = client.get("/")
    assert response.status_code == 200
    assert '<label' in response.text
    assert 'id="csv-file"' in response.text


# ---------------------------------------------------------------------------
# Valid upload
# ---------------------------------------------------------------------------

def test_valid_csv_upload_and_audit(client):
    csv = "name,age,city\nAlice,30,Nairobi\nBob,25,Buenos Aires\n"
    response = client.post(
        "/audit",
        files={"file": ("clean.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200
    assert "Audit results" in response.text
    assert "clean" in response.text
    assert "2" in response.text  # two data rows


def test_reuses_profiling_engine(client):
    """The web layer reuses dataguard.profile.load_csv/profile_rows directly."""
    csv = "name,status\nAlice,active\nBob,active\nCarol,active\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        f.write(csv)
        path = f.name
    try:
        rows = load_csv(path)
        result = profile_rows(rows)
        assert result.row_count == 3
        assert result.column_count == 2
        assert result.constant_columns == ["status"]
    finally:
        os.unlink(path)

    # Same data via the web endpoint should produce matching metrics.
    response = client.post(
        "/audit",
        files={"file": ("const.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200
    assert "3" in response.text  # three data rows
    assert "constant" in response.text.lower() or "1" in response.text


def test_duplicate_headers_distinguished_by_index(client):
    """Bug 4 workaround: duplicate column names shown with their index."""
    csv = "name,name,age\nA,1,30\nB,2,25\n"
    response = client.post(
        "/audit",
        files={"file": ("dup.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200
    # Both 'name' columns appear with distinct indices (0 and 1).
    assert "name" in response.text
    assert "index 0" in response.text or "0" in response.text


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------

def test_no_file_selected(client):
    response = client.post("/audit", data={})
    assert response.status_code == 400
    assert "select a csv file" in response.text.lower()


def test_non_csv_extension_rejected(client):
    response = client.post(
        "/audit",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "CSV" in response.text


def test_oversized_file_rejected_during_receipt(client):
    """A file over 10 MB is rejected before the engine reads it."""
    big = b"a\n" * ((MAX_UPLOAD_SIZE // 2) + 1)  # exceeds 10 MB
    response = client.post(
        "/audit",
        files={"file": ("big.csv", io.BytesIO(big), "text/csv")},
    )
    assert response.status_code == 413
    assert "too large" in response.text.lower()


def test_empty_file_rejected(client):
    response = client.post(
        "/audit",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert response.status_code == 400
    assert "empty" in response.text.lower()


def test_invalid_encoding_rejected(client):
    response = client.post(
        "/audit",
        files={"file": ("binary.csv", io.BytesIO(b"\xff\xfe\x00\x01"), "text/csv")},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------

def test_csv_derived_values_are_html_escaped(client):
    csv = "comment\n<script>alert(1)</script>\n"
    response = client.post(
        "/audit",
        files={"file": ("xss.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200
    # Escaped form present, raw script tag absent
    assert "&lt;script&gt;" in response.text
    assert "<script>" not in response.text


def test_no_traceback_in_error_response(client):
    response = client.post(
        "/audit",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400
    assert "Traceback" not in response.text
    assert "traceback" not in response.text.lower()


# ---------------------------------------------------------------------------
# Temp file cleanup
# ---------------------------------------------------------------------------

def _temp_dir_entries():
    temp_dir = Path(tempfile.gettempdir()) / "dataguard-uploads"
    if not temp_dir.exists():
        return set()
    return set(p.name for p in temp_dir.iterdir())


def test_temp_file_cleaned_up_after_success(client):
    before = _temp_dir_entries()
    csv = "name,age\nAlice,30\n"
    client.post(
        "/audit",
        files={"file": ("clean.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    after = _temp_dir_entries()
    assert before == after, f"Temp files left behind after success: {after - before}"


def test_temp_file_cleaned_up_after_error(client):
    before = _temp_dir_entries()
    client.post(
        "/audit",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    after = _temp_dir_entries()
    assert before == after, f"Temp files left behind after error: {after - before}"


def test_temp_file_cleaned_up_after_oversized(client):
    before = _temp_dir_entries()
    big = b"a\n" * ((MAX_UPLOAD_SIZE // 2) + 1)
    client.post(
        "/audit",
        files={"file": ("big.csv", io.BytesIO(big), "text/csv")},
    )
    after = _temp_dir_entries()
    assert before == after, f"Temp files left behind after oversized: {after - before}"


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

def test_preflight_rejects_header_over_column_limit(client):
    """A header with more than MAX_COLUMNS fields is rejected before load_csv."""
    header = ",".join(f"c{i}" for i in range(MAX_COLUMNS + 1)) + "\n"
    csv = header.encode("utf-8")
    with patch("web.routes.load_csv") as mock_load:
        response = client.post(
            "/audit",
            files={"file": ("many_cols.csv", io.BytesIO(csv), "text/csv")},
        )
    assert response.status_code == 400
    assert "too many columns" in response.text.lower()
    mock_load.assert_not_called()


def test_preflight_rejects_rows_over_row_limit(client):
    """More than MAX_ROWS data rows is rejected before load_csv."""
    header = "col\n"
    rows = "x\n" * (MAX_ROWS + 1)
    csv = (header + rows).encode("utf-8")
    with patch("web.routes.load_csv") as mock_load:
        response = client.post(
            "/audit",
            files={"file": ("many_rows.csv", io.BytesIO(csv), "text/csv")},
        )
    assert response.status_code == 400
    assert "too many rows" in response.text.lower()
    mock_load.assert_not_called()


def test_preflight_rejects_row_wider_than_column_limit(client):
    """A single row wider than MAX_COLUMNS is rejected before load_csv."""
    header = "a,b,c\n"
    wide_row = ",".join(f"v{i}" for i in range(MAX_COLUMNS + 1)) + "\n"
    csv = (header + wide_row).encode("utf-8")
    with patch("web.routes.load_csv") as mock_load:
        response = client.post(
            "/audit",
            files={"file": ("wide_row.csv", io.BytesIO(csv), "text/csv")},
        )
    assert response.status_code == 400
    assert "exceeding" in response.text.lower()
    mock_load.assert_not_called()


def test_preflight_allows_valid_csv_and_calls_engine(client):
    """A valid CSV passes preflight and load_csv IS called."""
    csv = "name,age\nAlice,30\nBob,25\n"
    with patch("web.routes.load_csv", side_effect=load_csv) as mock_load:
        response = client.post(
            "/audit",
            files={"file": ("clean.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
        )
    assert response.status_code == 200
    mock_load.assert_called_once()


# ---------------------------------------------------------------------------
# Timeout behaviour (best-effort; worker thread is not interrupted)
# ---------------------------------------------------------------------------


def test_timeout_returns_without_waiting_for_worker(client):
    """A slow audit returns a timeout response without waiting for the worker.

    The module-level executor is never shut down, so exiting the request does
    not block on ``executor.shutdown(wait=True)``. The worker may keep running
    in the background, but the HTTP response returns promptly.
    """
    real_profile_rows = profile_rows

    def slow_profile(rows):
        time.sleep(5)  # far longer than the 1s timeout below
        return real_profile_rows(rows)

    # routes.py bound AUDIT_TIMEOUT_SECONDS at import time, so patch it there.
    with patch("web.routes.profile_rows", side_effect=slow_profile), patch(
        "web.routes.AUDIT_TIMEOUT_SECONDS", 1
    ):
        start = time.monotonic()
        csv = "name,age\nAlice,30\n"
        response = client.post(
            "/audit",
            files={"file": ("slow.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
        )
        elapsed = time.monotonic() - start

    assert response.status_code == 400
    assert "too long" in response.text.lower()
    # If the request waited for the 5s worker, elapsed would be >= 5s.
    assert elapsed < 4, f"Request waited for the worker: {elapsed:.1f}s"


def test_subsequent_audit_not_blocked_after_timeout(client):
    """A timed-out audit must not prevent a later audit from running.

    With a per-request executor, a slow worker is abandoned after its timeout
    and cannot occupy the single worker slot of a shared pool. A second audit
    submitted immediately after should still complete successfully.
    """
    real_profile_rows = profile_rows
    call_count = {"n": 0}

    def slow_profile(rows):
        call_count["n"] += 1
        if call_count["n"] == 1:
            time.sleep(5)  # first audit hangs past the 1s timeout
        return real_profile_rows(rows)

    with patch("web.routes.profile_rows", side_effect=slow_profile), patch(
        "web.routes.AUDIT_TIMEOUT_SECONDS", 1
    ):
        # First audit: times out (worker sleeps 5s, request returns fast).
        slow_csv = "name,age\nAlice,30\n"
        r1 = client.post(
            "/audit",
            files={"file": ("slow.csv", io.BytesIO(slow_csv.encode("utf-8")), "text/csv")},
        )
        assert r1.status_code == 400
        assert "too long" in r1.text.lower()

        # Second audit: must complete successfully, not be blocked by the
        # still-running first worker.
        fast_csv = "name,age\nBob,25\n"
        r2 = client.post(
            "/audit",
            files={"file": ("fast.csv", io.BytesIO(fast_csv.encode("utf-8")), "text/csv")},
        )
        assert r2.status_code == 200, f"Second audit blocked: {r2.text}"
        assert "2" in r2.text  # one data row


# ---------------------------------------------------------------------------
# csv.field_size_limit() concurrency protection
# ---------------------------------------------------------------------------


def _write_temp_csv(content: str) -> str:
    with tempfile.NamedTemporaryFile(
        suffix=".csv", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(content)
        return f.name


def test_field_size_limit_restored_after_preflight_failure():
    """The process-global field size limit is restored even on parse failure."""
    original_limit = _csv.field_size_limit()
    big_field = "x" * (MAX_FIELD_SIZE + 1)
    path = _write_temp_csv(f"name\n{big_field}\n")
    try:
        with pytest.raises(UploadError):
            preflight_csv(path)
    finally:
        os.unlink(path)
    assert _csv.field_size_limit() == original_limit


def test_concurrent_preflight_restores_field_size_limit():
    """Multiple concurrent preflights each restore the field size limit.

    The per-thread observed limit is inherently racy (another thread may be
    mid-preflight when a thread reads it), so this test asserts only the
    final state after all threads have joined: the process-global limit must
    be back to its original value.
    """
    original_limit = _csv.field_size_limit()
    errors: list[BaseException] = []

    def run() -> None:
        try:
            big_field = "x" * (MAX_FIELD_SIZE + 1)
            path = _write_temp_csv(f"name\n{big_field}\n")
            try:
                try:
                    preflight_csv(path)
                except UploadError:
                    pass
            finally:
                os.unlink(path)
        except BaseException as exc:  # noqa: BLE001 - capture all thread errors
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent preflight raised errors: {errors}"
    assert _csv.field_size_limit() == original_limit


# ---------------------------------------------------------------------------
# Configuration values match design
# ---------------------------------------------------------------------------

def test_limits_match_design_document():
    assert MAX_UPLOAD_SIZE == 10 * 1024 * 1024  # 10 MB
    assert MAX_ROWS == 100_000
    assert MAX_COLUMNS == 1_000
    assert AUDIT_TIMEOUT_SECONDS == 30
