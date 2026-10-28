# DataGuard — Existing System Audit (Milestone 1)

**Workspace:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/`
**Application root:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/application/`
**Git repository root:** `/home/jabs101/Documents/career-lab/DataGuard-Workspace/` (workspace root contains `.git`; `application/.git` is nested inside it)
**Branch:** `main`
**Remote:** `https://github.com/Jabs007/dataguard.git`
**Python version:** 3.12.3 (venv at `application/.venv/`)
**Test result:** 50 passed in 0.24s (verified by running `python -m pytest`)

---

## 1. Current Architecture

DataGuard is a single-file Python package with a clean separation of concerns:

| Module | Responsibility | Key classes/functions |
|--------|---------------|----------------------|
| `dataguard/__init__.py` | Package metadata | `__version__ = "0.1.0"` |
| `dataguard/__main__.py` | `python -m dataguard` entry point | calls `cli.main()` |
| `dataguard/cli.py` | Argument parsing, terminal I/O, exit codes | `build_parser()`, `main()` |
| `dataguard/errors.py` | Custom exceptions | `DataGuardError`, `InvalidPathError`, `EncodingError`, `MalformedCSVError`, `EmptyFileError` |
| `dataguard/profile.py` | CSV loading, profiling engine, validation rules | `load_csv()`, `profile_rows()`, `apply_rules()`, `parse_expected_types()`, `_classify_cell()`, `_analyze_column()` |
| `dataguard/reports.py` | Text and JSON report rendering | `render_text()`, `render_json()`, `build_json_payload()` |

**Data flow:** `cli.main()` → `profile.load_csv()` → `profile.profile_rows()` → `profile.apply_rules()` → `reports.render_text()` / `reports.render_json()` → output (terminal or file).

The profile engine is deliberately side-effect free and CLI-independent so it can be unit-tested in isolation.

---

## 2. Verified Capabilities

All verified by running the test suite (50 tests) and manual CLI execution:

**CSV loading** (`profile.py:92-125` `load_csv()`):
- Reads CSV with stdlib `csv.reader` into lists of strings (not `DictReader`, to preserve duplicate headers)
- Default encoding `utf-8-sig` (strips leading BOM)
- Drops fully blank lines
- Raises `EmptyFileError` if no header row exists
- Raises `EncodingError` on undecodable bytes
- Raises `InvalidPathError` for missing path or non-regular file (e.g. directory)

**Profiling** (`profile.py:236-405` `profile_rows()`):
- Row count, column count
- Per-column analysis: dtype inference, missing count/pct, distinct count, constant flag, examples
- Duplicate header detection (before dict conversion, so no data loss)
- Duplicate row detection (exact tuple match, up to 5 examples)
- Ragged row detection (field count != header count)
- Constant column detection (exactly one distinct non-missing value)
- All-missing column detection (separate from constant)
- Human-readable `dataset_issues` list
- Structured `checks` dict shared by text and JSON reports

**Type inference** (`profile.py:140-174` `_classify_cell()`):
- Conservative: column gets one type only when every non-missing cell agrees; otherwise `mixed`
- Order: bool → date → datetime → int → float → string
- Types: `int`, `float`, `bool`, `date`, `datetime`, `string`, `mixed`, `empty`
- Mixed columns list up to 8 suspicious disagreeing values

**Validation rules** (`profile.py:438-502` `apply_rules()`):
- `--required-columns`: reports present/missing, status ok/failed
- `--expected-types`: per-column violation count, status ok/failed/skipped (column not found = skipped, never silent)

**Reports** (`reports.py`):
- Text report: human-readable summary, column table, dataset issues, checks, rules
- JSON report: stable schema (`tool`, `version`, `generated_at`, `input_file`, `encoding`, `delimiter`, `row_count`, `column_count`, `checks`, `rules`, `columns`, `dataset_issues`, `summary`)
- Same findings in both formats; only `generated_at` varies between runs

**CLI** (`cli.py:107-151` `main()`):
- Exit codes: 0 = success, 1 = runtime error, 2 = usage error (argparse)
- `-t` / `--report-text`: terminal (`-` or omitted) or file path
- `-j` / `--report-json`: terminal (`-`), file path, or default `<stem>.dataguard.json` next to input
- Never modifies or overwrites the input file
- Default JSON written next to the input CSV

---

## 3. Existing Limitations and Bugs

### Limitations (documented in README)

1. **Comma delimiter only** — `profile.py:43` `_DEFAULT_DELIMITER = ","` and `profile.py:390` `delimiter=","` hardcoded. No support for tab, semicolon, or other delimiters.
2. **Missing-value definition** — only empty or whitespace-only cells are missing. `NA`, `NULL`, `N/A` are not treated as missing (documented in README section "Known limitations").
3. **Conservative type inference** — a column is `mixed` if any cell disagrees; no threshold-based pass/fail.
4. **No configuration file** — rules passed via CLI flags only.

### Bugs found during audit

**Bug 1 — `learning/project-book/final_validation.py:23` references undefined class:**
```python
validator = SimpleHTMLParser()   # should be SimpleHTMLValidator
```
This will raise `NameError` when run. The file exists at `learning/project-book/final_validation.py`.

**Bug 2 — `application/clean.dataguard.json` and `application/messy.dataguard.json` at workspace root have `input_file: ""` and `encoding: ""`:**
These are stale generated reports (root-level `.dataguard.json` files) with empty metadata. They are gitignored (`*.dataguard.json`) but present on disk. Not source-code bugs, but worth noting as stale artifacts.

**Bug 3 — `application/-` file:**
A file named `-` exists in `application/` containing a text report (likely from running `dataguard -t -` redirect). It is not gitignored and not tracked. Should be cleaned up but is outside source code.

**Bug 4 — Duplicate headers cause `missing_by_column` key collision** (`profile.py:274`):
`missing_by_column = {col.name: col.missing_count for col in columns}` — if there are duplicate column names, the dict will collapse them, losing per-index missing counts. For `dupheader.csv` with header `name,name,age`, `missing_by_column` only has `{"name": 0, "age": 0}` (the second `name` overwrites the first). This is visible in `samples/dupheader.dataguard.json` lines 26-29 where only two keys appear for three columns.

**Bug 5 — `_classify_cell` treats `" 25 "` (with spaces) as int but does not strip before int() check** (`profile.py:164-166`):
`int(stripped)` — `stripped` is `text.strip()`, so `" 25 "` → `"25"` → int succeeds. This is actually correct. However, `examples` in `ColumnResult` uses raw `non_missing` values (e.g. `" 25 "` appears in `messy.dataguard.json` age examples). This is cosmetic but means examples may contain whitespace.

**Bug 6 — All-missing column dtype is `"empty"`** (`profile.py:211`):
An entirely-missing column gets `dtype="empty"` which is not in `TYPE_UNION`. This is intentional per tests (`test_all_missing_column_is_not_constant`) but `"empty"` is not a documented type in the README's type list (`int, float, bool, date, datetime, string`).

---

## 4. Existing Behavior That Must Remain Compatible

| Behavior | Source | Notes |
|----------|--------|-------|
| Exit codes 0/1/2 | `cli.py:107-151` | 0=success, 1=runtime error, 2=usage error |
| Comma delimiter only | `profile.py:43, 390` | No delimiter flag currently |
| `utf-8-sig` default encoding | `cli.py:48` | Strips BOM |
| Missing = empty or whitespace-only | `profile.py:147-149` | `NA`/`NULL` not missing |
| Conservative type inference | `profile.py:194-209` | `mixed` on any disagreement |
| Duplicate headers detected before dict conversion | `profile.py:246-265` | Prevents silent data loss |
| Input file never modified | `cli.py`, `tests/test_edge_cases.py` | Must remain true |
| Default JSON path next to input | `cli.py:88-90` | `<stem>.dataguard.json` |
| JSON schema keys | `reports.py:16-30` | Stable, documented |
| Text and JSON report same findings | `reports.py` | Only `generated_at` varies |
| `--required-columns` and `--expected-types` rules | `profile.py:438-502` | Skipped = column not found |

---

## 5. Test Coverage and Test Results

**Test files:**
- `application/tests/conftest.py` — fixtures: `clean_csv`, `messy_csv`, `constant_csv`, `dupheader_csv`, `empty_csv`, `missing_csv`
- `application/tests/test_cli.py` — 13 tests: CLI exit codes, report output, rules, missing file, invalid flags
- `application/tests/test_profile.py` — 12 tests: loading, classification, profiling, rules
- `application/tests/test_reports.py` — 5 tests: JSON structure, text/JSON agreement, column listing
- `application/tests/test_edge_cases.py` — 20 tests: empty files, header-only, blank lines, duplicate headers, all-missing columns, mixed types, ragged rows, invalid rules, unwritable destinations, input immutability

**Verified results:**
```
50 passed in 0.24s
```
All tests pass. Manual CLI run on `samples/messy.csv` produces correct text report matching README sample output.

**Coverage gaps (no tests for):**
- Encoding error via CLI (only via `load_csv` directly)
- Malformed CSV via `csv.reader` (e.g. unclosed quotes) — `MalformedCSVError` is defined but never raised in current code; `csv.reader` does not raise on malformed CSV, it yields what it can
- Oversized uploads / row/field limits
- Path traversal via filename
- Web upload workflow (doesn't exist yet)

---

## 6. Relevant Source Files and Line References

| File | Lines | Purpose |
|------|-------|---------|
| `application/dataguard/cli.py` | 1-155 | CLI entry, argument parsing, exit codes, main() |
| `application/dataguard/errors.py` | 1-21 | Custom exception hierarchy |
| `application/dataguard/profile.py` | 1-502 | CSV loading, profiling, type inference, validation rules |
| `application/dataguard/reports.py` | 1-158 | Text + JSON report rendering |
| `application/dataguard/__main__.py` | 1-6 | `python -m dataguard` entry |
| `application/dataguard/__init__.py` | 1-3 | Package version |
| `application/pyproject.toml` | 1-14 | Project metadata, pytest config |
| `application/tests/test_cli.py` | 1-112 | CLI tests |
| `application/tests/test_profile.py` | 1-188 | Profiling + rules tests |
| `application/tests/test_reports.py` | 1-65 | Report rendering tests |
| `application/tests/test_edge_cases.py` | 1-278 | Edge case tests |
| `application/tests/conftest.py` | 1-70 | Test fixtures |
| `application/samples/*.csv` | — | Fixture CSV files |
| `application/samples/*.dataguard.json` | — | Generated JSON report samples |

---

## 7. Risks and Unresolved Questions

1. **No delimiter support** — adding delimiter support would require threading a `delimiter` parameter through `load_csv()`, `profile_rows()`, and the JSON payload. Question: is comma-only acceptable for MVP, or is delimiter support required?

2. **Duplicate header `missing_by_column` collision** (`profile.py:274`) — dict keyed by name loses per-index data when headers are duplicated. Should `missing_by_column` be keyed by index or include duplicate names?

3. **`MalformedCSVError` defined but never raised** (`errors.py:16-17`) — `csv.reader` is lenient and doesn't raise on malformed input. Should we add strict CSV validation (e.g. checking for unclosed quotes)?

4. **`dtype="empty"` not in TYPE_UNION** (`profile.py:211`, `profile.py:41`) — all-missing columns get `"empty"` which is not a valid expected-type rule value. Inconsistency between inference output and rule input space.

5. **No file size limits** — `load_csv()` reads the entire file into memory (`list(csv.reader(handle))`). For a web upload endpoint, this is a DoS risk. Need a max upload size and streaming/bounded reads.

6. **No path traversal protection** — `load_csv()` takes any path. Web upload must sanitize filenames and write to a controlled temp directory.

7. **XSS risk** — CSV cell values are rendered into HTML/text reports. If we build a web UI, cell values containing `<script>` or HTML entities could be reflected unsanitized.

8. **Stale artifacts on disk** — `application/clean.dataguard.json`, `application/messy.dataguard.json`, and `application/-` are untracked/generated files cluttering the workspace root.

9. **`final_validation.py` NameError** — `SimpleHTMLParser()` vs `SimpleHTMLValidator` in `learning/project-book/final_validation.py:23`.

10. **Workspace reorganization** — `.git` is at workspace root, but `application/` has its own nested `.git` directory. `git status` from `application/` shows paths relative to root (`M ../learning/project-book/index.html`). Need to confirm whether `application/.git` is a separate repo or a leftover. Both `git log` calls show identical history, suggesting they point to the same objects.

---

## 8. Recommended Reuse vs. Refactoring

### Reuse (do not change)

| Component | Reason |
|-----------|--------|
| `profile.py` — `load_csv()`, `profile_rows()`, `apply_rules()`, `parse_expected_types()`, `_classify_cell()` | Pure, well-tested, side-effect free. The web layer should call these directly without duplicating logic. |
| `reports.py` — `build_json_payload()`, `render_json()` | The JSON payload is already structured and stable. The web API can reuse `build_json_payload()` as its response body. |
| `errors.py` exception hierarchy | Clean, sufficient for web layer error mapping (InvalidPathError → 400/404, EncodingError → 400, EmptyFileError → 400). |
| `cli.py` exit code contract (0/1/2) | Preserve for CLI compatibility. Web layer maps exceptions to HTTP status codes instead. |
| Test suite (50 tests) | Regression baseline. Must continue to pass after any web-layer changes. |

### Refactor / extend (for web layer)

| Change | Reason |
|--------|--------|
| Add `max_size` parameter to `load_csv()` or a wrapper | Prevent memory exhaustion on large uploads. |
| Sanitize filenames / write to temp dir | Web uploads must not write next to user input. |
| Escape CSV values for HTML output | Prevent XSS when rendering cell values in the browser. |
| Add `delimiter` parameter threading | If delimiter support is required beyond comma. |
| Separate web entry point from `cli.main()` | Keep CLI untouched; web app imports `profile` and `reports` directly. |

### Do not do

- Do not rewrite `profile.py` or `reports.py` from scratch.
- Do not add pandas, click, or other third-party runtime dependencies (README explicitly says stdlib-only).
- Do not modify the CLI unless a deliberate, tested change is justified.
- Do not add a database, authentication, or persistent report history without a concrete requirement.

---

## 9. Milestone 1 Complete

**Next checkpoint:** Milestone 2 — Product requirements and MVP scope (`learning/phase-2/02-product-requirements.md`).

**Evidence status:** All claims verified against source code and test execution. 50/50 tests passing. Manual CLI execution confirmed correct output.