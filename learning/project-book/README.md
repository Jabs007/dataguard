# DataGuard Project Learning Guide

A beginner-friendly, illustrated learning guide to the **DataGuard** CSV
data-quality auditor. DataGuard is a small, dependable command-line tool that
profiles a CSV file and produces a human-readable **text report** plus a
structured **JSON report** describing its data quality.

This guide explains what DataGuard does, how the system is architected, and
how to use it effectively. It is delivered as a single self-contained web
page (`index.html`) that runs entirely in the browser: no dependencies, no
build step, and no network access required.

---

## What this guide covers

The guide is organized into 15 main sections, each with detailed explanations,
code examples, and diagrams:

1. The big picture
2. The system at a glance
3. Repository tour
4. How to run it
5. The complete execution journey
6. Data flow
7. Module-by-module walkthrough
8. The core algorithms
9. Data structures and contracts
10. Testing and quality checks
11. Outputs and reporting
12. Failure scenarios and debugging
13. Security, reliability, and design trade-offs
14. Hands-on learning exercises
15. Glossary and learning roadmap

---

## How to use this guide

Each section explains the **what** (why it matters), the **how** (how the code
implements it, with file and line references), and **what to try** — a short
hands-on exercise to test your understanding.

- **Start at §1** if you are new to the tool.
- **Jump to §4** for the quick-start if you already know the basics and want to
  run DataGuard yourself.
- **Jump to §12** if you want to debug a messy CSV.

The running example throughout is `samples/messy.csv` — a deliberately messy
CSV that exercises nearly every check the tool performs.

---

## Repository structure

This project book lives in `learning/project-book/` and documents the DataGuard
application, which lives in the sibling folder `application/`.

```
learning/project-book/
├── index.html             # the complete project learning guide (self-contained)
├── README.md              # this file
├── assets/               # SVG fallbacks for the diagrams (used when no network)
├── detail/               # supplementary detail pages
├── illustrations/        # diagram illustrations
├── phase-2/              # phase-2 content
├── validate.py           # HTML validation helper
├── validate_html.py      # lightweight HTML parser validation helper
└── final_validation.py   # final end-to-end validation script

application/
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

---

## The DataGuard application

DataGuard runs from the command line. The package is built only on the Python
standard library (no third-party runtime dependencies); `pytest` is used only
as a development dependency.

Key responsibilities and their owners:

| Module | Responsibility |
|---|---|
| `dataguard/cli.py` | Command-line interface: argument parsing, running the pipeline, writing reports, exit codes. |
| `dataguard/profile.py` | CSV loading, per-column analysis, type inference, duplicate/missing/constant detection, rule validation. |
| `dataguard/reports.py` | Render the same findings as text and JSON reports. |
| `dataguard/errors.py` | Custom exceptions for path, encoding, CSV, and empty-file errors. |
| `dataguard/__main__.py` | Entry point for `python -m dataguard`. |

Run it from the `application/` folder after creating and activating the
project-local virtual environment:

```bash
/usr/bin/python3.12 -m venv .venv          # your system Python 3.12.3
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pytest
```

Then profile a CSV:

```bash
. .venv/bin/activate           # or use .venv/bin/python directly
python -m dataguard samples/clean.csv
python -m dataguard samples/messy.csv -j messy-report.json
python -m dataguard samples/messy.csv --required-columns name --expected-types age=int,score=int
```

See the `application/README.md` file for the full usage, sample output, and
exit-code reference.

---

## Rendering this guide

`index.html` is designed to work offline with no external dependencies:

- **Diagrams** are pure CSS flow layouts (no images, no scripts) with
  `assets/*.svg` as fallbacks when a user wants a graphic view.
- There are **no network dependencies**, so the guide renders identically in
  any modern browser, offline or online.
- The guide is responsive: it reflows to a single column on narrow screens.

---

## Validation

This guide has been validated to ensure:

- All file paths and line numbers reference actual repository content.
- All code examples match the actual implementation.
- All diagrams render correctly (or have clear SVG fallbacks).
- The accompanying DataGuard source files were not modified during creation.

---

## License

This learning guide is provided as-is for educational purposes. DataGuard
itself is licensed under the MIT License.
