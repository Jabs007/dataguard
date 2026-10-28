# DataGuard — Security and Privacy Design (Milestone 4)

**Workspace:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/`
**Application root:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/application/`
**Status:** Proposed design — not implemented. No application source files were modified.
**Depends on:** Milestone 1 audit (`learning/phase-2/01-existing-system-audit.md`), Milestone 2 requirements (`learning/phase-2/02-product-requirements.md`), Milestone 3 architecture (`learning/phase-2/03-architecture-design.md`)

---

## 1. Executive Summary

DataGuard treats every uploaded CSV as **untrusted input**. The security model is built on four principles:

1. **Never trust the client** — filename, MIME type, extension, cell values, and size are all untrusted.
2. **Never execute uploaded content** — files are stored as inert bytes, never interpreted or rendered as HTML by the server.
3. **Bound all resources** — size, row count, column count, and processing time are capped before the engine does expensive work.
4. **Leave no trace** — uploads exist only for the duration of a single request; temp files are cleaned up on success and failure; nothing is persisted to disk after the response is sent.

This document is a **design only**. No application code is changed and no dependencies are installed in this milestone.

---

## 2. Threat Model

### Assets to protect

| Asset | Why it matters |
|-------|----------------|
| Server filesystem | Uploads must not be able to write outside a controlled temp directory or overwrite application files. |
| Server memory and CPU | Malformed or oversized CSVs must not exhaust RAM or hang the process indefinitely. |
| User-uploaded data | Cell values may contain sensitive personal or business data; they must not leak into logs, error messages, or other users' views. |
| Browser clients | CSV-derived values rendered in HTML must not execute as scripts (XSS). |
| Report downloads | Generated JSON reports must be served with safe filenames and content types, never as executable content. |

### Threat actors

| Actor | Capabilities | Motivation |
|-------|-------------|------------|
| Malicious user | Uploads a crafted CSV, oversized file, or file with a malicious filename | Exfiltrate data, crash the server, execute code, plant XSS |
| Accidental user | Uploads a very large file, a binary file mislabeled as CSV, or a file in an unsupported encoding | Cause errors, confusion, or resource waste |
| Local attacker | Has filesystem access to the machine running DataGuard | Read temp files before cleanup (mitigated by randomized names and short lifetime) |

### Threats and mitigations

| ID | Threat | Mitigation | Verified vs. proposed |
|----|--------|------------|-----------------------|
| T-01 | Path traversal via filename (e.g. `../../etc/passwd`) | Filename sanitized before any filesystem use; stored under a randomized temp name inside a controlled directory | Proposed |
| T-02 | Upload fills disk or exhausts memory | Max upload size (10 MB) enforced before `load_csv()` reads contents | Proposed |
| T-03 | Very wide or tall file exhausts CPU/memory | Row limit (100k), column limit (1k) enforced after parse | Proposed |
| T-04 | Long-running audit hangs the request | Processing timeout (30s) around `profile_rows()` | Proposed |
| T-05 | CSV cell values render as executable HTML/XSS | All CSV-derived values HTML-escaped via Jinja2 auto-escaping | Proposed |
| T-06 | Uploaded file executed by server | Files stored as inert bytes; never interpreted, compiled, or rendered as HTML by the server | Proposed |
| T-07 | Sensitive cell values leaked in logs or error responses | Error messages reference sanitized filenames only; no cell values logged | Proposed |
| T-08 | Temp files left behind after failure | `try/finally` cleanup on success, exception, and timeout | Proposed |
| T-09 | Undecodable file causes traceback | `EncodingError` caught and mapped to HTTP 400 | Verified (engine raises `EncodingError`) |
| T-10 | Empty file causes crash | `EmptyFileError` caught and mapped to HTTP 400 | Verified (engine raises `EmptyFileError`) |
| T-11 | Report download served as executable HTML | Content type `application/json`, `Content-Disposition: attachment` | Proposed |
| T-12 | Duplicate headers hide per-column data | Web adapter iterates `result.columns` by index, bypassing name-keyed `missing_by_column` collision | Proposed (workaround for audit Bug 4) |
| T-13 | Malformed CSV not detected | `csv.reader` is lenient; unclosed quotes are accepted as data. Application does not claim to detect all malformed input. | Verified (engine limitation, audit Bug 3) |
| T-14 | Third-party dependency vulnerability | No new third-party runtime dependencies; stdlib-only like the existing engine | Proposed |

---

## 3. Upload and Parsing Limits

### Recommended limits (initial local MVP defaults)

| Limit | Default | Enforcement point | Rationale |
|-------|---------|-------------------|-----------|
| Max upload size | 10 MB | Before `load_csv()` reads contents | Prevents memory exhaustion from `list(csv.reader())` |
| Max data rows | 100,000 | After `load_csv()`, before `profile_rows()` | Bounds O(n) profiling work |
| Max columns | 1,000 | After `load_csv()`, before `profile_rows()` | Bounds per-column analysis memory |
| Max field length | No separate limit | Bounded indirectly by 10 MB total size cap | `csv.reader` handles long fields; overall cap suffices |
| Audit timeout | 30 seconds | Around `profile_rows()` execution | Prevents hung requests |

### Enforcement order (defense in depth)

1. **Extension check** — reject non-`.csv` filenames before any I/O.
2. **Size check** — inspect `UploadFile.size` or count bytes while streaming to temp file; reject > 10 MB with HTTP 413 before `load_csv()`.
3. **Filename sanitization** — strip path separators, reject `..` and absolute paths; generate randomized temp name.
4. **Write to temp file** — controlled temp directory, randomized name.
5. **`load_csv()`** — raises `InvalidPathError`, `EncodingError`, or `EmptyFileError` on bad input; mapped to HTTP 400.
6. **Row/column count check** — after parse, reject if `len(rows) - 1 > MAX_ROWS` or `len(header) > MAX_COLUMNS` with HTTP 400.
7. **`profile_rows()` with timeout** — 30s wall-clock; on timeout, HTTP 408/500 with clear message, temp file cleaned up.

### User communication when limits exceeded

| Limit exceeded | HTTP status | User-facing message |
|----------------|-------------|---------------------|
| Wrong extension | 400 | "Please upload a CSV file (.csv extension)." |
| Oversized file | 413 | "File is too large. Maximum size is 10 MB. Your file was X MB." |
| Too many rows | 400 | "File has too many rows. Maximum is 100,000 data rows." |
| Too many columns | 400 | "File has too many columns. Maximum is 1,000 columns." |
| Timeout | 408 or 500 | "The audit took too long to complete. Try a smaller file." |
| Bad encoding | 400 | "Could not read the file with encoding UTF-8. Please save the CSV as UTF-8 and try again." |
| Empty file | 400 | "The file is empty or has no header row." |

---

## 4. Data Retention

### Retention policy (MVP)

| Data | Retention | Disposal |
|------|-----------|----------|
| Uploaded CSV (temp file) | Duration of single HTTP request only | Deleted in `try/finally` after response sent or error |
| JSON report (temp file) | Not persisted; streamed directly to client | Not written to disk at all |
| Results page HTML | Rendered in response, not stored | Not stored |
| Logs | Sanitized filenames only; no cell values | Standard log rotation (deployment concern, out of MVP scope) |
| User session | None (stateless, no accounts) | N/A |

### Justification

- No database, no persistent report history, no user accounts (Milestone 2 exclusions).
- Files exist only for the duration of one request. This minimizes the window for local attackers to read temp files and eliminates the need for a data-retention schedule or deletion UI.
- If persistent storage is added post-MVP, a separate privacy assessment is required before any data is written to disk.

---

## 5. HTML Rendering and XSS Prevention

### Threat

CSV cell values are user-controlled. If a value such as `<script>alert(1)</script>` or `<img src=x onerror=...>` is rendered unescaped in the results table, it executes in the browser of anyone viewing that page.

### Controls

| Control | Implementation | Status |
|---------|---------------|--------|
| Jinja2 auto-escaping | All `{{ value }}` interpolations in templates are escaped by default | Proposed |
| No `|safe` filter on CSV data | Cell values, examples, suspicious values never marked safe | Proposed |
| Column names escaped | Header names are CSV-derived; escaped before rendering | Proposed |
| Duplicate row examples escaped | Joined cell strings (up to 5) escaped | Proposed |
| Suspicious values escaped | Mixed-type disagreeing values (up to 8) escaped | Proposed |
| No raw cell values in UI | Only limited examples shown, never full cell contents | Proposed |

### What is NOT protected against (acknowledged limitations)

- `csv.reader` does not validate CSV structure; unclosed quotes are accepted as data. The application does not claim to sanitize malformed CSV beyond what the engine already does.
- No Content Security Policy (CSP) in MVP — a reasonable hardening step for post-MVP, but not required for the local-first threat model.

---

## 6. Report Downloads

### Threat

A malicious filename could cause path traversal on the client, or a JSON response could be served with `text/html` content type and executed as HTML by the browser (content sniffing).

### Controls

| Control | Implementation |
|---------|---------------|
| Safe filename | `<sanitized-stem>.dataguard.json`; stem derived from uploaded filename after sanitization (no path separators, no `..`) |
| Content type | `application/json` |
| Content-Disposition | `attachment; filename="..."` — forces download, not inline rendering |
| No server path in JSON | `input_file` field contains sanitized filename only, never an absolute or server path |
| No sensitive data beyond engine defaults | JSON includes only existing `examples` (≤3 per column) and `suspicious` (≤8 per mixed column), matching CLI behavior |

---

## 7. Logging

### What is logged

| Item | Logged? | Reason |
|------|---------|--------|
| Sanitized filename | Yes | Helps operators correlate errors with uploads |
| HTTP status code | Yes | Standard request telemetry |
| Error type (category) | Yes | e.g. "encoding_error", "size_limit_exceeded" |
| File size (bytes) | Yes | Helps detect abuse patterns |
| Cell values | **No** | Sensitive data must not appear in logs |
| Full original filename | **No** | Could contain path traversal or identifying info |
| Stack traces | **No** in user responses; server logs may include them for debugging but must exclude cell values | Operational need, bounded |

### Log sanitization rule

All log messages referencing an upload must use the **sanitized** filename only. Cell values, row contents, and column data must never be interpolated into log strings.

---

## 8. Dependency Risks

### Existing dependencies (verified)

- Python standard library only at runtime (`csv`, `json`, `datetime`, `pathlib`, `dataclasses`, `argparse`)
- `pytest` is a development dependency only (not runtime)

### Proposed new dependencies (Milestone 5)

| Package | Purpose | Risk level | Mitigation |
|---------|---------|------------|------------|
| `fastapi` | Web framework | Low | Well-maintained, widely audited |
| `uvicorn` | ASGI server | Low | Standard for FastAPI |
| `jinja2` | Template rendering | Low | Auto-escaping enabled by default |
| `python-multipart` | Form file uploads | Low | Required for `UploadFile` |

### Dependency policy

- No third-party **runtime** dependencies are added to the existing `dataguard/` engine (it remains stdlib-only).
- Web dependencies are confined to the new `application/web/` layer.
- All dependencies pinned in `pyproject.toml` with exact versions (Milestone 5).
- No `pandas`, `click`, or other heavy frameworks (consistent with README's stated design).

---

## 9. Security Tests

The following tests must be added in Milestone 6. All are automated unless marked manual.

| Test ID | Scenario | Expected result | Automated? |
|---------|----------|-----------------|------------|
| SEC-01 | Upload `.txt`, `.xlsx`, `.exe` | HTTP 400, rejected before parsing | Yes |
| SEC-02 | Upload file > 10 MB | HTTP 413, rejected before `load_csv()` | Yes |
| SEC-03 | Upload 0-byte file | HTTP 400, clear error, no temp file remains | Yes |
| SEC-04 | Upload undecodable binary as `.csv` | HTTP 400, encoding error, no traceback | Yes |
| SEC-05 | Filename `../../etc/passwd.csv` | Sanitized, stored under safe temp name, no path traversal | Yes |
| SEC-06 | Filename with spaces and special chars | Sanitized, safe download filename | Yes |
| SEC-07 | Cell value contains `<script>alert(1)</script>` | Rendered escaped in HTML, not executed | Yes |
| SEC-08 | Cell value contains `"><img src=x onerror=...>` | Escaped, no script execution | Yes |
| SEC-09 | Temp file exists after successful upload | No temp file remains on disk | Yes |
| SEC-10 | Temp file exists after engine error | No temp file remains on disk | Yes |
| SEC-11 | Temp file exists after timeout | No temp file remains on disk | Yes |
| SEC-12 | Oversized file leaves no temp file | Rejected at size check, nothing written to disk | Yes |
| SEC-13 | Report download content type | `application/json` | Yes |
| SEC-14 | Report download filename | `<sanitized-stem>.dataguard.json`, `.dataguard.json` extension | Yes |
| SEC-15 | Log messages contain no cell values | Review log output for cell-value leakage | Manual (code review) |
| SEC-16 | Error responses contain no traceback details | Generic message only, no stack trace | Yes |
| SEC-17 | Duplicate headers distinguished by index | Both `name` columns shown with index 0 and 1 | Yes |

### Test data policy

- All security tests use synthetic test data created in `tmp_path`.
- No real sensitive datasets are used in tests.
- No test data is uploaded to external services.

---

## 10. Local vs. Public Deployment Requirements

| Requirement | Local MVP | Public deployment (post-MVP) |
|-------------|-----------|------------------------------|
| Authentication | None required | Required (deferred) |
| Rate limiting | None required | Required (deferred) |
| Persistent storage | None | Requires privacy assessment (deferred) |
| HTTPS | Not applicable (localhost) | Required (deferred) |
| Security headers | Not required | CSP, HSTS, X-Frame-Options (deferred) |
| Audit logging | Minimal, sanitized | Comprehensive, retention policy (deferred) |

---

## 11. Assumptions and Unresolved Questions

### Verified existing behavior (from Milestone 1)

- `load_csv()` raises `InvalidPathError`, `EncodingError`, `EmptyFileError` on bad input — all caught by `cli.main()` and mapped to exit code 1.
- `MalformedCSVError` is defined in `errors.py` but never raised (audit Bug 3 — `csv.reader` is lenient).
- `missing_by_column` is name-keyed and collapses duplicate headers (audit Bug 4).
- All 50 existing tests pass.
- No third-party runtime dependencies.

### Assumptions requiring confirmation

1. **10 MB default upload size** — adequate for target users; confirm with feedback.
2. **30-second timeout** — sufficient for files within row/column limits; confirm by measuring.
3. **Warning-only severity** — acceptable because engine has no `error` level; confirm users don't need differentiated severity.
4. **Local-first threat model** — no multi-user isolation needed; confirm before any public deployment.

### Unresolved questions (deferred to implementation or post-MVP)

- Temp directory location: OS temp (`/tmp`) vs. application-managed directory.
- Timeout implementation: `signal.alarm()` (Unix-only) vs. `ThreadPoolExecutor` with `future.result(timeout=)`.
- Whether to fix `missing_by_column` in the engine post-MVP (schema change risk).
- Whether to add CSP and other security headers post-MVP.

---

## 12. Completion Report

**Document created:**
`/home/jabs101/Documents/career-lab/DataGuard-Workspace/learning/phase-2/04-security-and-privacy-design.md`

**Major security decisions:**
- All uploads treated as untrusted; filename, MIME type, extension, and cell values never trusted.
- Max upload size 10 MB enforced before engine reads contents; row/column limits after parse; 30s timeout.
- Temp files: randomized names, controlled directory, `try/finally` cleanup on success, error, and timeout.
- No persistent storage; files exist only for the duration of one request.
- All CSV-derived values HTML-escaped via Jinja2 auto-escaping; no `|safe` on CSV data.
- Report downloads: `application/json`, `Content-Disposition: attachment`, sanitized filename.
- Logging: sanitized filenames only; no cell values, no stack traces in responses.
- No new third-party runtime dependencies for the engine; web dependencies confined to `application/web/`.
- `csv.reader` leniency acknowledged — not all malformed CSVs detectable; application does not claim full detection.

**Files created:**
- `learning/phase-2/04-security-and-privacy-design.md`

**Files modified:** None (design document only).

**Confirmation:** No application source files under `application/dataguard/` were modified. No dependencies installed. No Git metadata changed. No push to GitHub. No implementation begun — design document only.

Milestone 4 is complete. Ready for review before proceeding to Milestone 5 (incremental implementation).