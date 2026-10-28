# DataGuard — Architecture Design (Milestone 3)

**Workspace:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/`
**Application root:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/application/`
**Status:** Proposed design — not implemented. No application source files were modified.
**Depends on:** Milestone 1 audit (`learning/phase-2/01-existing-system-audit.md`), Milestone 2 requirements (`learning/phase-2/02-product-requirements.md`)

---

## 1. Executive Recommendation

**Recommended architecture:** FastAPI with server-rendered Jinja2 HTML templates. A single Python process serves the upload form, receives the CSV, runs the existing profiling engine synchronously, renders the results page, and serves a JSON report download.

**Why FastAPI + server-rendered templates:**

| Criterion | FastAPI + templates | Flask + templates | FastAPI + separate JS frontend |
|-----------|---------------------|-------------------|-------------------------------|
| Fit with existing Python engine | Excellent — sync engine called directly via `run_in_threadpool` | Excellent — same | Poor — requires JSON API layer + frontend build step |
| Implementation complexity | Low — one process, no build tooling | Low — same | High — two codebases, CORS, API contracts, build pipeline |
| Learning value | High — modern async framework, still simple | Moderate — older pattern | Moderate — but split across backend/frontend |
| Upload handling & security | Excellent — `UploadFile`, size limits, temp files | Good — similar | Good — but adds API surface |
| Testing & maintainability | High — `TestClient`, dependency injection, one codebase | Good — test client available | Moderate — backend + frontend tests |
| Dependency footprint | Moderate — fastapi, uvicorn, jinja2, python-multipart | Low — flask, jinja2 | High — backend + npm/node frontend |
| Local run on Linux Mint | Simple — `uvicorn app:app --reload` in venv | Simple — `flask run` | Complex — backend + frontend dev servers |
| Accessibility & responsive UI | Full control via server-rendered HTML | Full control | Full control but more moving parts |
| Solves a real MVP requirement? | Yes — browser upload + results + download | Yes | Yes, but over-engineered for MVP |

**Decision:** FastAPI with Jinja2 server-rendered templates. This keeps the entire product in one Python codebase, reuses the existing engine without an API boundary, avoids a frontend build step, and delivers the full MVP user journey (upload → results → download) with the fewest moving parts. A separate JavaScript frontend is rejected because it adds complexity (build tooling, CORS, API contracts, two test suites) without solving any MVP requirement that server-rendered HTML cannot meet.

**No database, authentication, background workers, or public API** — none are required by the MVP requirements (Milestone 2). The product is single-user, local-first, synchronous, and stateless.

---

## 2. Compared Options

### Option A: FastAPI + Jinja2 server-rendered templates (RECOMMENDED)

One Python package serves HTML pages and JSON downloads. The profiling engine is called synchronously within the request handler (FastAPI runs sync endpoints in a threadpool).

**Pros:**
- Single codebase, single test suite, one dependency set
- Reuses `profile_rows()` and `build_json_payload()` directly — no JSON API translation layer
- FastAPI's `UploadFile` gives size-limit hooks before file contents reach the engine
- `TestClient` enables integration tests of the full upload → results → download flow
- Jinja2 templates give full control over HTML semantics, ARIA attributes, and responsive CSS

**Cons:**
- Requires adding `fastapi`, `uvicorn`, `jinja2`, `python-multipart` as dependencies (Milestone 5)
- Async framework with a sync engine requires `run_in_threadpool` (minor adapter)

### Option B: Flask + Jinja2 server-rendered templates

Same structure as Option A but with Flask instead of FastAPI.

**Pros:**
- Slightly smaller dependency footprint (flask + jinja2)
- Familiar, synchronous request model — no threadpool adapter needed

**Cons:**
- Flask is in maintenance mode; fewer modern features (type-based dependency injection, automatic OpenAPI)
- Upload size enforcement is less ergonomic than FastAPI's `UploadFile`
- Smaller long-term community momentum

**Verdict:** Rejected. FastAPI offers better type safety, cleaner dependency injection, and better upload handling with negligible added complexity for this MVP.

### Option C: FastAPI + separate JavaScript frontend (e.g. React/Vue)

Backend exposes JSON API; frontend is a separate SPA.

**Pros:**
- Decoupled frontend/backend
- Rich client-side interactivity (not needed for MVP)

**Cons:**
- Two codebases, two test suites, two build pipelines
- CORS configuration, API versioning, frontend build tooling (node/npm)
- More surface area for security issues (API endpoints + frontend)
- No MVP requirement justifies client-side interactivity — the user journey is linear: upload, wait, view, download

**Verdict:** Rejected. Over-engineered for the MVP. Could be reconsidered later only if real user needs emerge.

---

## 3. Component Architecture

### Component responsibilities

| Component | Responsibility | Depends on |
|-----------|---------------|------------|
| **Browser UI** | Upload form, results page, findings table, download button; all HTML rendered server-side | Jinja2 templates + minimal CSS |
| **HTTP routes (controllers)** | `GET /` (upload form), `POST /audit` (validate + profile + render results), `GET /report/<token>.json` (download) | FastAPI, upload module, adapter |
| **Upload validation** | Extension check, size limit, empty-file check, encoding pre-check, safe temp file creation | Python stdlib (`tempfile`, `os`) |
| **Temporary file handling** | Randomized temp filenames, controlled temp dir, guaranteed cleanup via `try/finally` | `tempfile`, `contextlib` |
| **Profiling engine** | `profile.load_csv()`, `profile.profile_rows()`, `profile.apply_rules()` — called unchanged | Existing `dataguard/profile.py` |
| **Web adapter** | Converts `ProfileResult` into web-friendly view models (findings list with plain-language explanations, severity labels, column context) | New `web/adapter.py` |
| **Report construction** | `reports.build_json_payload()` — called unchanged; serialized to JSON for download | Existing `dataguard/reports.py` |
| **JSON report download** | Stream `build_json_payload()` output as `application/json` with `Content-Disposition: attachment` | FastAPI `Response` |
| **Error handling** | Map `DataGuardError` subclasses → HTTP 400; size limit → 413; unexpected → 500 with no sensitive details | FastAPI exception handlers |
| **Configuration** | `MAX_UPLOAD_SIZE` (10 MB), `MAX_ROWS` (100,000), `MAX_COLUMNS` (1,000), `AUDIT_TIMEOUT` (30s), temp dir path | Environment variables or a small settings module |

### Request/data flow (plain text)

1. Browser `GET /` → server renders upload form (HTML).
2. User selects a CSV and submits `POST /audit` (multipart/form-data).
3. Server validates: file present, `.csv` extension, size ≤ limit, filename sanitized.
4. Server writes upload to a randomized temp file in a controlled temp directory.
5. Server calls `profile.load_csv(temp_path)` → raises `InvalidPathError`/`EncodingError`/`EmptyFileError` on bad input.
6. Server calls `profile.profile_rows(rows)` → produces `ProfileResult`.
7. Server calls `profile.apply_rules(result, ...)` if rules were provided.
8. Web adapter converts `ProfileResult` → view model (findings list, summary metrics).
9. Server renders `results.html` with the view model.
10. User clicks "Download report" → `GET /report/<token>.json` → server calls `reports.build_json_payload(result)` → returns JSON file download.
11. `try/finally` deletes the temp file on success, error, or client disconnect.

### Mermaid diagram

```mermaid
flowchart TD
    User[User / Browser] -->|GET /| Form[Upload Form Page]
    Form -->|POST /audit + CSV file| Validate[Upload Validation]
    Validate -->|Invalid| ErrorPage[Error Page]
    Validate -->|Valid| TempFile[Write to randomized temp file]
    TempFile -->|load_csv()| Engine[Profiling Engine: profile_rows() + apply_rules()]
    Engine -->|Engine error| ErrorPage
    Engine -->|ProfileResult| Adapter[Web Adapter: findings + summary]
    Adapter -->|View model| Results[Results HTML Page]
    Results -->|Download report| Report[GET /report/<token>.json]
    Report -->|build_json_payload()| JSON[JSON file download]
    TempFile -->|try/finally cleanup| Cleanup[Temp file deleted]
    Cleanup --> User
    ErrorPage -->|Try again| Form
```

**Plain-text explanation:** The user opens the upload form, submits a CSV, and the server validates it before writing to a randomized temp file. The existing profiling engine audits the file. If the engine succeeds, a web adapter turns the result into a findings table and summary, rendered as HTML. The user can download a JSON report. The temp file is deleted in a `finally` block regardless of success or failure.

---

## 4. Integration with the Existing CLI Project

### Reuse without duplication

The web application imports and calls existing modules directly — no copying, no reimplementation:

| Web-layer call | Existing function | Source |
|----------------|-------------------|--------|
| Load and parse CSV | `profile.load_csv(path, encoding)` | `dataguard/profile.py:92` |
| Profile the dataset | `profile.profile_rows(rows)` | `dataguard/profile.py:236` |
| Apply validation rules | `profile.apply_rules(result, required_columns, expected_types)` | `dataguard/profile.py:438` |
| Build JSON report payload | `reports.build_json_payload(result)` | `dataguard/reports.py:46` |
| Error types | `DataGuardError`, `InvalidPathError`, `EncodingError`, `EmptyFileError`, `MalformedCSVError` | `dataguard/errors.py` |

The CLI (`cli.py`) continues to work unchanged. The web app is a separate entry point (`web/app.py`) that imports from `dataguard.*` but does not import from `dataguard.cli`.

### Interface mismatches and adapter needs

**Mismatch 1 — `ProfileResult` contains `non_missing` (internal, not serialised):**
`ColumnResult.non_missing` is explicitly excluded from report serialization (marked `repr=False` and documented as internal). The web adapter must not expose `non_missing` in the UI or JSON. It should only use the public report fields: `name`, `index`, `dtype`, `missing_count`, `missing_pct`, `distinct_count`, `is_constant`, `is_duplicate`, `suspicious`, `examples`.

**Mismatch 2 — `missing_by_column` is keyed by name and collapses duplicates:**
`profile.py:274` builds `missing_by_column = {col.name: col.missing_count for col in columns}`. With duplicate headers, later entries overwrite earlier ones. For `dupheader.csv` (`name,name,age`), the dict has only `{"name": 0, "age": 0}` instead of three entries.

**Recommendation: Web-layer workaround (do not modify the engine for MVP).**

The web adapter iterates `result.columns` directly and builds a list of `{"index": c.index, "name": c.name, "missing_count": c.missing_count}` tuples. This preserves per-index data for duplicate columns without touching the shared engine. The engine's `missing_by_column` remains unchanged for CLI backward compatibility.

**Rationale for not fixing the engine:** Changing `missing_by_column` from a name-keyed dict to an index-keyed structure would alter the documented JSON schema (`samples/*.dataguard.json` show name-keyed dicts). Existing tests and consumers depend on that shape. A schema change is a backward-compatibility risk not justified for MVP. The web-layer workaround is strictly additive and isolated.

**Mismatch 3 — Engine raises exceptions; web layer needs HTTP status codes:**
The web layer maps exceptions:
- `InvalidPathError` → HTTP 400 (bad upload)
- `EncodingError` → HTTP 400 (bad encoding)
- `EmptyFileError` → HTTP 400 (empty file) — but note: empty file with header is valid; only truly empty files raise this
- `MalformedCSVError` → HTTP 400 (currently never raised by `csv.reader`; see Section 5)
- `ValueError` from `apply_rules` (bad rule token) → HTTP 400
- Size limit exceeded → HTTP 413
- Unexpected exception → HTTP 500 with generic message (no traceback details)

---

## 5. Resource and CSV-Processing Decisions

### Recommended initial limits (local MVP defaults)

| Limit | Default | Justification |
|-------|---------|---------------|
| Max upload size | 10 MB | Covers typical analyst/student extracts; prevents memory exhaustion from `list(csv.reader())` |
| Max rows | 100,000 | Profiling is O(n); 100k rows completes well within timeout on modest hardware |
| Max columns | 1,000 | Wide files are rare in CSV audits; bounds memory for column analysis |
| Max field length | No explicit limit | `csv.reader` handles long fields; memory is bounded by overall 10 MB cap |
| Audit timeout | 30 seconds | Sufficient for files within the above limits; prevents hung requests |

### Enforcement approach

1. **Size limit (before parse):** Check `UploadFile.size` (or read the stream in chunks and count bytes) before calling `load_csv()`. Reject with HTTP 413 and a clear message if exceeded. This satisfies UP-07: rejected before the engine processes contents.
2. **Row/column limits (after parse):** After `load_csv()` returns rows, check `len(rows) - 1 ≤ MAX_ROWS` and `len(header) ≤ MAX_COLUMNS`. Reject with HTTP 400 if exceeded.
3. **Timeout:** Wrap `profile_rows()` in a timeout. Options:
   - `signal.alarm()` (Unix-only, works on Linux Mint)
   - `concurrent.futures.ThreadPoolExecutor` with `future.result(timeout=30)`
   - FastAPI's `run_in_threadpool` with a wrapper

   **Recommendation:** `ThreadPoolExecutor` with `timeout=30` — works cross-platform, integrates with FastAPI's sync endpoint threadpool.

### CSV reader behavior with malformed input

`csv.reader` is deliberately lenient:

| Input | `csv.reader` behavior | Detectable by engine? |
|-------|----------------------|----------------------|
| Undecodable bytes | `UnicodeDecodeError` → caught, re-raised as `EncodingError` | Yes |
| Empty file (0 bytes) | `rows` is empty → `EmptyFileError` | Yes |
| Header only | 1 row → valid, 0 data rows | Yes (accepted) |
| Unclosed quote | `csv.reader` reads to end of file, does not raise | **No** — accepted as suspicious data |
| Extremely long line | Read into memory; bounded by 10 MB size limit | Partially |
| Mixed delimiters within a row | Treated as part of field values | **No** — accepted |
| NUL bytes | May be included in cells | **No** — accepted |

**Important:** The application cannot detect every malformed CSV. `MalformedCSVError` is defined in `errors.py` but never raised (audit Bug 3). The web layer should not claim to detect all malformed input. Detectable failures are: undecodable bytes, empty file, invalid path. Everything else is treated as data and profiled accordingly, which is the existing engine's documented behavior.

---

## 6. Safe Upload and Report Handling

### Filename and path safety

| Threat | Control |
|--------|---------|
| User-controlled filename in storage path | Sanitized: strip path separators (`/`, `\`), remove `..`, reject absolute paths; store under a randomized temp name, not the original name |
| Path traversal | Temp file path is always inside the controlled temp directory; original filename never used in filesystem operations |
| Filename collision | `tempfile.NamedTemporaryFile(dir=..., delete=False)` with random suffix; or `uuid4().hex` + `.csv` |
| MIME type trust | MIME type and extension are treated as untrusted; extension check is a coarse filter, not a safety guarantee |

### Content safety

| Threat | Control |
|--------|---------|
| XSS from cell values in HTML | All CSV-derived values rendered via Jinja2 `{{ value }}` (auto-escapes by default); `examples` and `suspicious` values escaped |
| Spreadsheet formula injection | CSV is never opened in a spreadsheet application; cell values are treated as plain text only |
| Executable content | Uploaded files are never executed, interpreted, or rendered as HTML by the server |
| Sensitive values in logs | Error messages reference sanitized filenames only; no cell values logged |
| Sensitive values in reports | JSON report includes only existing `examples` (≤3 per column) and `suspicious` (≤8 per mixed column), matching CLI behavior |

### Cleanup guarantees

```python
# Conceptual pattern (not implemented):
temp_path = None
try:
    temp_path = write_upload_to_temp(upload_file)
    result = profile_rows(load_csv(temp_path))
    ...
finally:
    if temp_path and os.path.exists(temp_path):
        os.unlink(temp_path)
```

Cleanup runs on: success, validation error, engine error, timeout, unexpected exception. No temp files persist after the request completes.

### Report download safety

- Filename: `<sanitized-stem>.dataguard.json` (stem derived from uploaded filename, sanitized)
- Content type: `application/json`
- Content-Disposition: `attachment; filename="..."`
- `input_file` in JSON payload: sanitized filename only, never a server path

### Edge cases handled

| Case | Behavior |
|------|----------|
| Empty file (0 bytes) | `EmptyFileError` → HTTP 400, clear message |
| Header-only file | Valid → 0 data rows, summary shows 0 rows |
| Duplicate headers | Detected by engine; web adapter shows name + index for each |
| Ragged rows | Detected by engine; count shown in summary |
| Unexpected engine error | HTTP 500, generic message, temp file cleaned up |
| Processing exceeds timeout | HTTP 408 or 500, clear message, temp file cleaned up |

---

## 7. Proposed Project Structure

New code is added under `application/web/`. Existing files under `application/dataguard/` are unchanged.

```
application/
├── dataguard/              # EXISTING — unchanged
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # unchanged CLI entry point
│   ├── errors.py           # unchanged
│   ├── profile.py          # unchanged (Bug 4 workaround in web layer)
│   └── reports.py          # unchanged
├── web/                    # NEW — web layer
│   ├── __init__.py
│   ├── app.py              # FastAPI app factory, exception handlers, settings
│   ├── routes.py           # GET /, POST /audit, GET /report/<token>.json
│   ├── upload.py           # upload validation, temp file creation/cleanup
│   ├── adapter.py          # ProfileResult → web view model
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html      # upload form
│   │   └── results.html    # summary + findings table + download
│   └── static/
│       └── style.css       # minimal responsive CSS
├── tests/
│   ├── test_cli.py         # EXISTING — unchanged
│   ├── test_profile.py     # EXISTING — unchanged
│   ├── test_reports.py     # EXISTING — unchanged
│   ├── test_edge_cases.py  # EXISTING — unchanged
│   └── test_web/           # NEW
│       ├── test_upload.py
│       ├── test_adapter.py
│       ├── test_routes.py
│       └── test_security.py
├── samples/                # EXISTING — unchanged
├── pyproject.toml          # MODIFIED — add fastapi, uvicorn, jinja2, python-multipart (Milestone 5)
├── .gitignore              # EXISTING — maybe add web temp dir (Milestone 5)
└── README.md               # EXISTING — maybe updated later (Milestone 7)
```

**Files expected to change in implementation (Milestone 5):**
- `pyproject.toml` — add web dependencies
- `application/web/` — all new files (created)
- `application/tests/test_web/` — all new test files (created)
- `.gitignore` — possibly add web temp directory pattern

**Files NOT changed:**
- `application/dataguard/cli.py`
- `application/dataguard/profile.py`
- `application/dataguard/reports.py`
- `application/dataguard/errors.py`
- `application/dataguard/__init__.py`
- `application/dataguard/__main__.py`
- `application/tests/test_cli.py`
- `application/tests/test_profile.py`
- `application/tests/test_reports.py`
- `application/tests/test_edge_cases.py`

---

## 8. Testing Architecture

### Test layers

| Layer | What it covers | Automated? |
|-------|---------------|------------|
| Unit tests (web) | Adapter logic, upload validation, filename sanitization, size checks | Yes |
| Integration tests (web) | Full flow: upload → audit → results → download; temp cleanup on success/failure | Yes (`TestClient`) |
| Regression tests (CLI) | Existing 50 tests must still pass | Yes |
| Manual tests | Accessibility, responsive layout, loading/error/empty states in a real browser | No |

### Important test cases

| Test | Scenario | Expected |
|------|----------|----------|
| Successful upload | Valid CSV → results page shows summary + findings | HTTP 200, correct metrics |
| JSON report download | Download link returns JSON with correct name/type | HTTP 200, `application/json`, `.dataguard.json` |
| Missing file | No file selected | HTTP 400, clear error |
| Wrong extension | `.txt`, `.xlsx`, `.exe` | HTTP 400, rejected before parsing |
| Oversized upload | File > 10 MB | HTTP 413, rejected before engine reads contents |
| Empty file | 0 bytes | HTTP 400, clear error |
| Bad encoding | Undecodable bytes | HTTP 400, encoding error |
| Malformed CSV | Unclosed quotes | Engine accepts (lenient `csv.reader`); no crash |
| Duplicate headers | `name,name,age` | Findings show both `name` columns distinguished by index |
| Ragged rows | Rows with != field count | Count shown in summary |
| Temp cleanup success | After successful audit | No temp file remains |
| Temp cleanup failure | After engine error | No temp file remains |
| HTML escaping | Cell value contains `<script>` | Rendered escaped, not executed |
| Path traversal | Filename `../../etc/passwd` | Sanitized, stored under safe temp name |
| Row limit exceeded | > 100,000 rows | HTTP 400, clear message |
| Unexpected exception | Engine raises unhandled error | HTTP 500, generic message, no sensitive details |

### Verification of no regression

The existing 50 CLI tests (`test_cli.py`, `test_profile.py`, `test_reports.py`, `test_edge_cases.py`) must continue to pass unchanged. The web tests are additive and do not touch CLI code paths.

---

## 9. Risks, Assumptions, Deferred Decisions, Rejected Alternatives

### Verified existing behavior (from Milestone 1)

- `profile_rows()` produces all summary metrics (DS-01..DS-13)
- `build_json_payload()` produces a stable JSON schema
- `ColumnResult.index` tracks column position for duplicate columns
- `missing_by_column` is name-keyed and collapses duplicates (Bug 4)
- All 50 existing tests pass
- `csv.reader` is lenient; `MalformedCSVError` is never raised (Bug 3)

### Assumptions requiring confirmation

1. **10 MB max upload, 100k rows, 1,000 columns, 30s timeout** — assumed adequate; confirm with user feedback after MVP
2. **`run_in_threadpool` for sync engine** — acceptable performance for files within limits
3. **Warning-only severity** — acceptable because engine has no `error` level

### Deferred decisions (Milestone 3+)

| Decision | Deferred to | Reason |
|----------|-------------|--------|
| Web framework final selection | Milestone 5 implementation | Documented here; FastAPI recommended but not yet committed |
| Temp directory location (OS temp vs. app temp) | Milestone 5 | Depends on deployment context |
| Timeout implementation (signal vs. ThreadPoolExecutor) | Milestone 5 | Both viable; choose at implementation |
| Whether to fix `missing_by_column` in engine later | Post-MVP | Schema change risk; web-layer workaround suffices for MVP |
| Public cloud deployment | Post-MVP | Local instance first |

### Rejected alternatives

- **Flask:** Rejected in favor of FastAPI (better type safety, upload handling, modern maintenance)
- **Separate JS frontend:** Rejected (over-engineered for MVP; no requirement justifies it)
- **Database/persistent storage:** Rejected (no MVP requirement; privacy implications unassessed)
- **Authentication/accounts:** Rejected (single-user local product)
- **Background workers/async processing:** Rejected (synchronous is sufficient for ≤10 MB files)
- **Public API:** Rejected (browser UI is the interface)
- **Engine fix for `missing_by_column`:** Rejected for MVP (backward-compatibility risk; web-layer workaround is sufficient)

---

## 10. Completion Report

**Document created:**
`/home/jabs101/Documents/career-lab/DataGuard-Workspace/learning/phase-2/03-architecture-design.md`

**Recommended architecture:**
FastAPI + Jinja2 server-rendered HTML templates, single Python process, synchronous profiling engine called directly, JSON report download via the same process. No database, auth, background workers, or public API.

**Major decisions:**
- FastAPI recommended over Flask and FastAPI+JS frontend (single codebase, no build step, direct engine reuse)
- Web-layer workaround for `missing_by_column` duplicate-header collision (no engine change for MVP)
- Temp files: randomized names, controlled directory, `try/finally` cleanup on all paths
- Limits: 10 MB upload, 100k rows, 1,000 columns, 30s timeout (initial MVP defaults)
- `csv.reader` leniency acknowledged — not all malformed CSVs are detectable
- All CSV-derived values HTML-escaped; no raw cell values exposed by default

**Unresolved questions:**
1. Exact limit values (10 MB, 100k rows, 1k columns, 30s) — to be confirmed with user feedback
2. Timeout implementation method (signal vs. ThreadPoolExecutor)
3. Temp directory location (OS temp vs. application-managed)
4. Whether to fix `missing_by_column` in the engine post-MVP

**Files created:**
- `learning/phase-2/03-architecture-design.md` (this document)

**Files modified:** None (planning document only).

**Confirmation:** No application source files under `application/dataguard/` were modified. No dependencies installed. No Git metadata changed. No push to GitHub. No implementation begun — this is a design document only.

Milestone 3 is complete. Ready for review before proceeding to Milestone 4 (security and privacy design).