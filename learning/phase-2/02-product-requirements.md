# DataGuard — Product Requirements and MVP Scope (Milestone 2)

**Workspace:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/`
**Application root:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/application/`
**Source of truth:** Milestone 1 audit (`learning/phase-2/01-existing-system-audit.md`) and the existing source under `application/dataguard/`

**Status:** Proposed — not implemented. No application source files were modified.

---

## 1. Product Vision and Target Users

### Product vision

DataGuard is a browser-accessible CSV data-quality auditing tool. A user uploads a CSV, the server audits it using the existing profiling engine, and the user sees a clear data-quality summary, inspects individual findings, and downloads a structured report.

The product builds on the existing CLI engine (`profile.py`, `reports.py`, `errors.py`) without duplicating business logic or rewriting it from scratch.

### Target users

| User | Problem | Primary need |
|------|---------|--------------|
| Individual data analyst | Receives messy CSVs from colleagues or external sources; needs a fast way to spot quality problems before analysis | Upload one file, see a summary of issues, download a report |
| Data science student | Learning data cleaning; needs understandable explanations of what is wrong and why | Plain-language findings, suggested remediation, no jargon |
| Small team | Shares CSV files informally; no budget for enterprise data-quality platforms | Zero-config, no accounts, no database, instant results |

### Out of scope for target users

- Enterprise teams needing persistent report history, user accounts, role-based access, or audit trails
- Teams needing scheduled/background audits of production datasets
- Users needing to audit non-CSV formats (Excel, JSON, Parquet)

---

## 2. User Journeys

### Journey 1 — Happy path: upload and review

1. User opens DataGuard in a browser.
2. User sees an upload area with a "Choose CSV file" button and a drag-and-drop zone.
3. User selects a CSV file and submits.
4. The application validates the upload (file type, size, encoding) and runs the audit engine.
5. User sees a loading state while the audit runs.
6. On success, user sees a data-quality summary: row/column counts, missing values, duplicate rows, constant columns, mixed-type columns, ragged rows.
7. User inspects a findings table with one row per finding, each showing type, severity, column context, count, plain-language explanation, and suggested remediation.
8. User downloads a JSON report.
9. User can upload another file or navigate away.

### Journey 2 — Error path: invalid upload

1. User selects a non-CSV file (e.g. `.exe`, `.xlsx`) or a CSV that is empty, malformed, or uses an unsupported encoding.
2. User submits.
3. The application rejects the upload before running the audit engine.
4. User sees a clear, plain-language error message explaining what was wrong and what to do.
5. No temporary files are left behind.

### Journey 3 — Error path: oversized upload

1. User selects a CSV larger than the configured maximum.
2. The application rejects the upload before parsing its contents.
3. User sees a message stating the size limit and how large their file was.
4. No temporary files are left behind.

---

## 3. MVP Scope and Exclusions

### MVP (in scope for first release)

| Area | Included |
|------|----------|
| File upload | CSV only (`.csv` extension); single file per upload |
| File validation | Extension check, size limit, encoding check, empty-file check, malformed-CSV check |
| Auditing | Reuse of existing `profile_rows()` engine: row/column counts, missing values, duplicate rows, duplicate headers, constant columns, all-missing columns, ragged rows, mixed types |
| Rules | `--required-columns` and `--expected-types` (mapped from existing CLI flags to form inputs) |
| Summary view | Metrics from `ProfileResult.summary` plus per-column table |
| Findings view | One row per finding with type, severity, column context, count, explanation, remediation |
| Report download | JSON report reuse of `build_json_payload()`; downloadable file with `.dataguard.json` extension |
| Error states | Missing file, empty file, bad encoding, malformed CSV, oversized file, unwritable destination |
| Privacy | Uploads processed in a temp directory with guaranteed cleanup; no persistent storage |

### Explicitly out of scope (Later or Deferred)

| Feature | Group | Reason |
|---------|-------|--------|
| Persistent report history | Later | Requires database + privacy assessment; not needed for first release |
| User accounts / authentication | Later | Single-user, local-first product; no multi-user isolation needed yet |
| Background jobs / async processing | Later | MVP handles small-to-medium files synchronously; add if audit time becomes a problem |
| Public API | Later | Not justified by target users; the browser UI is the interface |
| Reusable saved validation rules | Later | CLI already supports ad-hoc rules; save/load adds config management complexity |
| Team collaboration / sharing | Later | No accounts, no persistence; sharing means re-uploading |
| Non-CSV formats (Excel, JSON, Parquet) | Deferred/rejected | Engine is CSV-only; adding formats requires new parsing logic |
| Custom delimiters (tab, semicolon) | Deferred/rejected | Engine hardcodes comma (audit Bug: `profile.py:43`); not a blocker for MVP |
| Universal data-quality score | Deferred/rejected | README explicitly avoids inventing a score; transparent counts/percentages preferred |
| Configuration file for missing-value tokens (`NA`, `NULL`) | Later | Documented limitation in README; not requested by target users |
| Deployment to a public cloud | Later | Local development instance first; deployment decided in Milestone 3 |

---

## 4. Functional Requirements

### A. Upload workflow

| ID | Requirement | Priority |
|----|-------------|----------|
| UP-01 | The application accepts a single file upload via a browser form. | Must |
| UP-02 | Only files with a `.csv` extension are accepted. Other extensions are rejected before parsing. | Must |
| UP-03 | A missing upload (no file selected) produces a clear error: "Please select a CSV file to upload." | Must |
| UP-04 | An empty file (0 bytes or header-only with no data rows) is accepted and audited; header-only files produce 0 data rows. | Must |
| UP-05 | A malformed CSV (e.g. unclosed quotes that break `csv.reader`) produces a clear error rather than a traceback. | Must |
| UP-06 | An unsupported encoding produces a clear error identifying the problem. | Must |
| UP-07 | A configurable maximum upload size is enforced. Uploads exceeding the limit are rejected before the audit engine processes the contents. | Must |
| UP-08 | The maximum upload size default is 10 MB. Justification: target users (analysts, students) typically audit small-to-medium extracts; 10 MB covers typical CSVs while preventing memory exhaustion from `list(csv.reader())` loading the whole file. | Must |
| UP-09 | Excessive row counts, column counts, and field lengths are bounded. If a file exceeds a configured row limit (e.g. 100,000 rows) or column limit (e.g. 1,000 columns), the upload is rejected with a clear message. | Must |
| UP-10 | Audit processing time is bounded. If the engine exceeds a configured timeout (e.g. 30 seconds), the request fails with a clear error. | Must |
| UP-11 | While the audit runs, the user sees a loading state. On completion, the user sees either results or an error. | Must |
| UP-12 | On success, the user sees a data-quality summary and a findings table. | Must |
| UP-13 | On failure, the user sees a clear error message and can try again with a different file. | Must |
| UP-14 | No temporary files are left behind after a successful or failed upload. | Must |

### B. Data-quality summary

| ID | Requirement | Priority | Source status |
|----|-------------|----------|---------------|
| DS-01 | Total row count (data rows, excluding header) is displayed. | Must | Supported by engine (`profile_rows.row_count`) |
| DS-02 | Total column count is displayed. | Must | Supported by engine (`profile_rows.column_count`) |
| DS-03 | Missing-value count and percentage per column are displayed. | Must | Supported by engine (`ColumnResult.missing_count`, `missing_pct`) |
| DS-04 | Duplicate-row count is displayed. | Must | Supported by engine (`duplicate_row_count`) |
| DS-05 | Duplicate-column (header) count is displayed. | Must | Supported by engine (`duplicate_columns`) |
| DS-06 | Constant-column count is displayed. | Must | Supported by engine (`constant_columns`) |
| DS-07 | All-missing-column count is displayed. | Must | Supported by engine (`all_missing_columns`) |
| DS-08 | Ragged-row count is displayed. | Must | Supported by engine (`ragged_rows`) |
| DS-09 | Mixed-type column count is displayed. | Must | Supported by engine (`columns` with `dtype == "mixed"`) |
| DS-10 | Total missing-cell count is displayed. | Must | Supported by engine (`total_missing`) |
| DS-11 | No universal data-quality score is invented. Transparent counts and percentages are used instead. | Must | Engine does not produce a score; none should be added |
| DS-12 | Per-column inferred data type is displayed (int, float, bool, date, datetime, string, mixed, empty). | Must | Supported by engine (`ColumnResult.dtype`) |
| DS-13 | Duplicate column names are distinguished by index (position) in the findings table. | Must | Engine already tracks `ColumnResult.index` |

**Metrics requiring adaptation:** None for the summary — all DS metrics map directly to existing `ProfileResult` fields. The web layer will adapt the presentation but not the computation.

**New validation capabilities needed:** None for MVP. All required metrics are produced by the existing engine.

### C. Findings inspection

| ID | Requirement | Priority |
|----|-------------|----------|
| FI-01 | Each finding exposes: finding type, severity, column or row context, count, percentage affected, plain-language explanation, suggested remediation. | Must |
| FI-02 | Finding types map to existing engine checks: `missing_values`, `duplicate_rows`, `duplicate_columns`, `constant_columns`, `all_missing_columns`, `ragged_rows`, `type_inference`, plus rule violations (`required_columns`, `expected_types`). | Must |
| FI-03 | Severity is `warning` for all findings in MVP. Rationale: the engine already classifies checks as `ok`/`warning`; there is no `error` severity in the engine, and introducing one would require new logic not justified for MVP. | Must |
| FI-04 | Column context uses the column name and index (position). For duplicate column names, both name and index are shown so they can be distinguished. | Must |
| FI-05 | Full raw cell values are not exposed by default. Only up to 3 example values per column (from `ColumnResult.examples`) may be shown, and they are HTML-escaped. | Must |
| FI-06 | Row-level details (e.g. "row 5 has a problem") are not promised. The engine reports aggregate counts and duplicate-row examples (up to 5 joined strings), not per-row finding locations. | Must |
| FI-07 | Duplicate row examples (up to 5) are shown as joined cell strings, HTML-escaped. | Must |
| FI-08 | Suspicious values from mixed-type columns (up to 8) are shown as examples, HTML-escaped. | Must |

### D. Reports

| ID | Requirement | Priority |
|----|-------------|----------|
| RP-01 | The MVP produces a JSON report only. The existing text report remains CLI-only. | Must |
| RP-02 | The JSON report reuses `build_json_payload()` from `reports.py` without modification. | Must |
| RP-03 | The JSON schema is the existing stable schema: `tool`, `version`, `generated_at`, `input_file`, `encoding`, `delimiter`, `row_count`, `column_count`, `checks`, `rules`, `columns`, `dataset_issues`, `summary`. | Must |
| RP-04 | `input_file` in the report reflects the uploaded filename (sanitized), not a server path. | Must |
| RP-05 | `generated_at` is an ISO-8601 UTC timestamp (existing behavior). | Must |
| RP-06 | The report is downloadable as a file named `<original-stem>.dataguard.json`. | Must |
| RP-07 | Content type is `application/json`. | Must |
| RP-08 | No sensitive cell values are included beyond the existing `examples` (up to 3 per column) and `suspicious` (up to 8 per mixed column), both already limited and HTML-escaped for display. | Must |
| RP-09 | On report generation failure, the user sees a clear error and no partial file is left behind. | Must |

### E. Privacy and security

| ID | Requirement | Priority | Local vs. public |
|----|-------------|----------|------------------|
| PR-01 | Uploaded CSVs are treated as untrusted input. | Must | Both |
| PR-02 | Maximum upload size is enforced (default 10 MB) before the engine reads file contents. | Must | Both |
| PR-03 | Uploads are written to a controlled temporary directory, never next to user input or in the application directory. | Must | Both |
| PR-04 | Temporary files use randomized names to prevent collisions and prediction. | Must | Both |
| PR-05 | Filenames are sanitized: path separators removed, `..` blocked, no absolute paths. | Must | Both |
| PR-06 | No path traversal is possible via the uploaded filename. | Must | Both |
| PR-07 | All CSV-derived values rendered in the browser are HTML-escaped to prevent XSS. | Must | Both |
| PR-08 | Temporary files are cleaned up on success and on failure (including engine errors and timeouts). | Must | Both |
| PR-09 | No persistent storage of uploaded files or reports. Files exist only for the duration of the request. | Must | Local instance |
| PR-10 | Error messages and logs do not include full cell values or sensitive data. Filenames may be logged but are sanitized. | Must | Both |
| PR-11 | No executed content: uploaded files are never interpreted, rendered as HTML, or executed by the server. | Must | Both |
| PR-12 | Dependency safety: no third-party runtime dependencies are added (stdlib-only, matching existing engine). | Must | Both |
| PR-13 | For public deployment (deferred), rate limiting and authentication would need reassessment. Not required for local development instance. | Deferred | Public only |

### F. Accessibility and usability

| ID | Requirement | Priority |
|----|-------------|----------|
| AC-01 | The upload control is keyboard-navigable (Tab to focus, Enter/Space to activate). | Must |
| AC-02 | The file input has a visible `<label>` associated via `for`/`id`. | Must |
| AC-03 | Error messages are announced and visually distinct (color + icon/text, not color alone). | Must |
| AC-04 | The findings table uses `<table>` with `<thead>` and `<th>` scope attributes for screen readers. | Must |
| AC-05 | Layout is responsive: usable on mobile and desktop without horizontal scrolling. | Must |
| AC-06 | Loading state is visible and descriptive ("Auditing your CSV…"). | Must |
| AC-07 | Empty state (no findings) is shown clearly with a message such as "No data-quality issues detected." | Must |
| AC-08 | Explanations use plain language suitable for a data science student (e.g. "Column 'city' has the same value in every row" rather than "Constant column detected"). | Must |
| AC-09 | All interactive elements have visible focus indicators. | Must |

---

## 5. Requirements and Acceptance-Criteria Matrix

| ID | User / business need | Requirement | Priority | Acceptance criteria | Verification method | Dependencies / unresolved |
|----|----------------------|-------------|----------|---------------------|---------------------|---------------------------|
| UP-01 | User needs to upload a CSV via browser | Single-file upload form | Must | Form submits to server; server receives file | Manual test + integration test | None |
| UP-02 | Only CSV files should be audited | `.csv` extension required | Must | `.txt`, `.xlsx`, `.exe` rejected with "Please upload a CSV file" | Unit test + manual test | None |
| UP-03 | No file selected should not crash | Missing upload error | Must | Error message shown; no audit runs | Unit test + manual test | None |
| UP-04 | Empty/header-only files are valid CSVs | Empty file accepted | Must | Header-only file audited with 0 data rows; no crash | Unit test | None |
| UP-05 | Malformed CSV should not crash server | Malformed CSV error | Must | Clear error, no traceback, exit handled gracefully | Unit test | `csv.reader` leniency — may need strict validation |
| UP-06 | Bad encoding should be reported | Encoding error | Must | Undecodable file produces clear encoding error | Unit test | Engine already raises `EncodingError` |
| UP-07 | Large files should not exhaust memory | Max upload size enforced | Must | File > 10 MB rejected before engine reads contents | Integration test | Need to confirm size-check placement (before `load_csv`) |
| UP-08 | Default limit is sensible | 10 MB default | Must | Configurable; default 10 MB | Config inspection | None |
| UP-09 | Very wide/tall files should be bounded | Row/column/field limits | Must | >100k rows or >1,000 columns rejected with clear message | Unit test | Limits not yet defined in engine |
| UP-10 | Long-running audits should not hang | Timeout | Must | Audit > 30s fails with clear error | Integration test | Not implemented in engine yet |
| UP-11 | User needs feedback during audit | Loading state | Must | Loading indicator visible while audit runs | Frontend test | None |
| UP-12 | User needs results on success | Summary + findings | Must | Summary and findings table displayed | Integration test | None |
| UP-13 | User needs to recover from failure | Error state | Must | Clear error; retry possible | Manual test | None |
| UP-14 | Disk should not fill with temp files | Cleanup | Must | No temp files remain after success or failure | Integration test | None |
| DS-01..DS-13 | User needs to understand data quality | Summary metrics displayed | Must | All metrics match engine output exactly | Unit test comparing UI values to `ProfileResult` | None |
| FI-01..FI-08 | User needs to inspect findings | Findings table | Must | Each finding has type, severity, context, count, explanation, remediation | Unit test + manual test | None |
| RP-01..RP-09 | User needs to download a report | JSON report download | Must | JSON file downloaded with correct name, content type, schema | Integration test | None |
| PR-01..PR-13 | Data must be handled safely | Security controls | Must | Temp files cleaned, filenames sanitized, values escaped, no persistent storage | Security test + code review | None |
| AC-01..AC-09 | All users can use the tool | Accessibility | Must | Keyboard navigable, labeled inputs, escaped table, responsive | Manual accessibility check | None |

---

## 6. Assumptions, Risks, and Unresolved Questions

### Verified existing behavior (from Milestone 1 audit)

- The profile engine (`profile_rows`) produces all DS-01..DS-13 metrics directly.
- `build_json_payload()` produces a stable JSON schema.
- `ColumnResult` tracks `index` so duplicate columns can be distinguished.
- `missing_by_column` is keyed by column name, which collapses duplicate headers (audit Bug 4).
- All 50 existing tests pass.

### Assumptions requiring confirmation

1. **Max upload size of 10 MB** — assumed adequate for target users. Confirm with user feedback after MVP.
2. **Row limit of 100,000 and column limit of 1,000** — assumed reasonable bounds. Confirm based on typical user file sizes.
3. **Timeout of 30 seconds** — assumed sufficient for CSV profiling on small-to-medium files. Confirm after measuring.
4. **Warning as the only severity** — assumed acceptable because the engine has no `error` severity. Confirm users don't need differentiated severity.

### Decisions deferred to Milestone 3 (architecture)

- Web framework choice (FastAPI, server-rendered templates, or separate JS frontend).
- How file size limits are enforced (middleware, WSGI/ASGI layer, or manual check before `load_csv`).
- Where temporary files are stored (OS temp dir vs. application temp dir).
- How timeouts are implemented (signal, thread, or framework-native).
- Whether `missing_by_column` duplicate-header collision (Bug 4) is fixed before MVP or worked around in the web layer.

### Risks

- `csv.reader` is lenient and may not raise on all malformed CSVs; `MalformedCSVError` is defined but never raised (audit Bug 3). The web layer may need additional validation.
- `load_csv()` reads the entire file into memory (`list(csv.reader())`). For files near the 10 MB limit this is acceptable, but larger files would need streaming (out of MVP scope).
- No existing tests cover security scenarios (path traversal, oversized uploads, XSS). These must be added in Milestone 6.

---

## 7. Definition of MVP Completion

The MVP is complete when all of the following are true:

1. A user can open DataGuard in a browser, upload a `.csv` file, and see a data-quality summary and findings table.
2. All DS-01..DS-13 metrics displayed in the UI match the output of the existing `profile_rows()` engine for the same file.
3. Invalid uploads (missing file, wrong extension, empty, malformed, bad encoding, oversized) produce clear errors without crashing and without leaving temp files.
4. A JSON report can be downloaded with the correct filename, content type, and schema.
5. All existing 50 CLI tests still pass (no regression to the CLI).
6. New tests cover: upload validation, error states, report download, temp-file cleanup, filename sanitization, HTML escaping of cell values.
7. No application source code under `application/dataguard/` was modified (only new web-layer code added).
8. No database, authentication, background workers, or persistent storage was added.

---

## Completion Report

**File created:**
`/home/jabs101/DataGuard-Workspace/learning/phase-2/02-product-requirements.md`

**Main MVP decisions:**
- Single-file CSV upload via browser form; `.csv` extension only.
- Reuse the existing `profile_rows()` engine and `build_json_payload()` unchanged — no duplication of business logic.
- JSON report only for download; text report remains CLI-only.
- Max upload size 10 MB (configurable), enforced before the engine reads contents.
- Temp files in a controlled directory with randomized names and guaranteed cleanup; no persistent storage.
- Warning as the only severity (engine has no `error` severity).
- No universal data-quality score; transparent counts and percentages only.
- All cell values HTML-escaped; no full raw cell values exposed by default.

**Explicitly out of scope:**
- Persistent report history, user accounts, authentication, background jobs, public API, reusable saved rules, team collaboration, non-CSV formats, custom delimiters, universal quality score, configuration file for missing-value tokens, public cloud deployment.

**Most important unresolved questions:**
1. Web framework choice (FastAPI vs. server-rendered templates vs. separate JS frontend) — deferred to Milestone 3.
2. Whether `missing_by_column` duplicate-header collision (audit Bug 4) is fixed before MVP or worked around — deferred to Milestone 3.
3. Exact row/column/field limits and timeout values — assumed defaults, to be confirmed with user feedback.
4. How `csv.reader` leniency affects malformed-CSV detection — may require additional validation.

**Acceptance criteria verification:**
- Unit tests: individual requirements (extension check, size limit, encoding error, cleanup).
- Integration tests: full upload → audit → findings → download workflow.
- Manual tests: accessibility, loading/error/empty states, responsive layout.
- Regression: existing 50 CLI tests must still pass.

**Confirmation:** No application source files under `application/dataguard/` were modified. No dependencies installed. No Git metadata changed. No files moved or deleted. No push to GitHub.

Milestone 2 is complete. Ready for review before proceeding to Milestone 3 (architecture and technical design).