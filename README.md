# DataGuard

A small, dependable command-line tool that profiles a CSV file and produces a
human-readable **text report** and a structured **JSON report** describing its
data quality.

---

## 1. The problem DataGuard addresses

CSV files used in data analysis or ML pipelines frequently carry quality problems
that are easy to miss and expensive to fix downstream:

- missing values (empty cells, whitespace-only cells, etc.)
- duplicate rows, or duplicate column headers
- constant columns (one distinct value) and all-missing columns
- columns whose values mix types (e.g. `88`, `95`, `abc`)
- a header row that accidentally repeats names

DataGuard's job is to **detect these issues up front** and report them clearly,
so a data engineer or analyst can decide what to fix before loading the file.

## Intended users

- Data Science graduates and junior analysts building software-engineering
  skills (the programme that produced this tool).
- Anyone who wants a fast, dependency-free, command-line CSV audit that never
  silently drops data.

---

## 2. Features

- Reads a CSV safely with the Python standard library only.
- Reports row and column counts.
- Detects missing values **per column** (empty or whitespace-only cells are
  treated as missing).
- Detects duplicate rows and duplicate column headers.
- Detects constant columns and all-missing columns.
- Infers a conservative column data type and flags mixed/suspicious values.
- Supports optional required-column and expected-type rules.
- Produces both a readable text report and a JSON report with the same findings.
- Provides a useful CLI (help text, required args, meaningful exit codes).
- **Never modifies or overwrites the input file.**

## Known limitations

- Zero runtime dependencies — only the Python standard library is used at
  runtime. No `pandas`, `click`, etc. (those can be added later).
- The CSV **delimiter is comma**; other delimiters are not supported yet.
- Whitespace-only cells are treated as missing. Values like `NA` / `NULL` are
  **not** treated as missing unless explicitly handled in a future version.
- Type inference is deliberately **conservative**. A column is reported as one
  type only when every non-missing cell agrees; otherwise it is flagged as
  mixed/suspicious. Ambiguous data is surfaced, not treated as invalid.
- An expected-type rule whose column does not exist is reported as
  `skipped` (a typo is surfaced in the text report, not hidden).

---

## 3. Requirements and installation

- **Python 3.11 or newer** (verified on Python 3.12.3).
- **No third-party runtime dependencies.** Only the standard library is used.
- `pytest` is a *development* dependency only.

Create the project-local virtual environment from your system Python and install
`pytest` into it:

```bash
# From the project root (dataguard/)
/usr/bin/python3.12 -m venv .venv          # your system Python 3.12.3
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pytest
```

The `.venv/` directory and all `*.dataguard.json` files are ignored by
`.gitignore`, so nothing virtual, cached, or generated is tracked.

---

## 4. How to run the tool

Activate the virtual environment, then run with `python -m dataguard`:

```bash
. .venv/bin/activate        # or use .venv/bin/python directly
dataguard --help
dataguard --version
```

Say `python -m dataguard` works the same way when the venv is active:

```bash
python -m dataguard samples/clean.csv
```

### Examples

Profile a clean sample:

```bash
python -m dataguard samples/clean.csv
```

Profile a messy sample (writes reports to the terminal and a default JSON file):

```bash
python -m dataguard samples/messy.csv
```

Specify a text report file and a JSON report file:

```bash
python -m dataguard samples/messy.csv -t messy.txt -j messy-report.json
```

Apply required-column and expected-type rules:

```bash
python -m dataguard samples/messy.csv \
  --required-columns name \
  --expected-types age=int,score=int
```

Use `-` as the report target to write to the terminal:

```bash
python -m dataguard -t - -j - samples/messy.csv
```

---

## 5. Sample output

Running `python -m dataguard samples/messy.csv` produces a text report like:

```
DataGuard — CSV data-quality report
==============================================
Input file : samples/messy.csv
Encoding   : utf-8-sig
Delimiter  : ,
Rows       : 6
Columns    : 4

Summary
----------------------------------------------
  Duplicate rows            : 1
  Duplicate columns         : 0
  Constant columns          : 1
  All-missing columns       : 0
  Columns with missing      : 4
  Columns with mixed type   : 1
  Total missing cells       : 8

Columns
----------------------------------------------
Name                   IdxType        Missing  Dist  Const  Dupd  Sample
name                     0string            1     3      -      -  Alice,Bob,Carol
age                      1int               2     3      -      -  30,25
score                    2mixed             2     3      -      -  88,95,abc
city                     3string               3     1      yes  -  Nairobi

Dataset issues
----------------------------------------------
  - 1 row(s) are exact duplicates of an earlier row.
  - 1 row(s) have a different number of fields than the header (4).
  - 8 missing cell(s) across 4 column(s): name, age, score, city.
  - 1 constant column(s): city.
  - 1 column(s) have mixed or ambiguous types: score.

Checks
----------------------------------------------
  row_count              ok       6 row(s) read.
  columns                ok       4 column(s) found.
  missing_values         warning  8 missing cell(s) across 4 column(s).
  duplicate_rows         warning  1 duplicate row(s) found.
  duplicate_columns      ok       0 duplicate header name(s).
  constant_columns       warning  1 constant column(s).
  type_inference         warning  1 column(s) have mixed or ambiguous types.

Rules
----------------------------------------------
  required_columns : ok
  expected_types   : ok
```

The JSON report (`samples/messy.dataguard.json`) contains the **same findings**
under a stable, documented schema (`checks`, `rules`, `columns`, `summary`,
`dataset_issues`, plus metadata like `generated_at`).

---

## 6. How to run the tests

```bash
.venv/bin/python -m pytest
```

---

## 7. Project structure

```
dataguard/
├── dataguard/                      # the Python package
│   ├── cli.py          # CLI parsing, exit codes, main() (terminal I/O only)
│   ├── errors.py       # custom exceptions
│   ├── __init__.py     # package metadata (__version__)
│   ├── __main__.py     # python -m dataguard entry point
│   ├── profile.py      # CSV loading + profiling engine (no CLI dependency)
│   └── reports.py      # text + JSON report rendering
├── samples/        # small CSV fixtures for manual runs
├── tests/          # pytest suite
├── pyproject.toml  # project metadata, stdlib-only
├── .gitignore
└── README.md
```

## Missing-value, type-inference, report, and exit-code policy

- **Missing values**: a cell is missing when it is empty or contains only
  whitespace. Values such as `NA` / `NULL` are **not** treated as missing
  automatically.
- **Type inference**: conservative. A column reports one primitive type
  (`int`, `float`, `bool`, `date`, `datetime`, `string`) only when every
  non-missing cell agrees; otherwise it is `mixed` and disagreeing cells are
  listed as `suspicious`.
- **Reports**: text and JSON describe the same findings. Only
  `generated_at` varies between runs. Keys are stable and documented above.
- **Exit codes**: `0` = success, `1` = runtime error, `2` = usage error.

## Future improvements (not implemented)

- Support other CSV delimiters and quote styles.
- Configuration file for rules and missing-value tokens (`NA`, `NULL`, …).
- `pandas`-based type inference for richer pattern analysis.
- Optional CLI flags for `compliance` checks and threshold-based pass/fail.
- A `--strict` mode that treats ambiguous type columns as failures.

---

*DataGuard is a learning project, not a production data-quality platform. Treat
the test suite as a correctness signal for this scope, not as a guarantee of
production readiness.*
