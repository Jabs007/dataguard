"""Command-line interface for DataGuard.

The interface separates pure understanding from terminal I/O:

* ``dataguard.profile`` reads and profiles the CSV.
* ``dataguard.reports`` renders the findings.
* This module only parses arguments, prints to the terminal, and writes output
  files. It can be (and is) tested without touching the filesystem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import DataGuardError
from .profile import apply_rules, load_csv, profile_rows
from .reports import render_json, render_text

DEFAULT_DELIMITER = ","


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataguard",
        description=(
            "DataGuard: a small, dependable command-line CSV data-quality auditor. "
            "Reads a CSV file, profiles it, and writes a human-readable text report "
            "and a JSON report."
        ),
        epilog=(
            "Exit codes: 0 = success (findings reported), "
            "1 = runtime error, 2 = usage error."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "csv",
        help="Path to the CSV file to audit.",
    )
    parser.add_argument(
        "-e",
        "--encoding",
        default="utf-8-sig",
        help="Text encoding (default: utf-8-sig, which strips a leading BOM if present).",
    )
    parser.add_argument(
        "-t",
        "--report-text",
        default=None,
        help=(
            "Write a human-readable report to this path (default: print to the "
            "terminal; the single character minus also means stdout)."
        ),
    )
    parser.add_argument(
        "-j",
        "--report-json",
        default=None,
        help=(
            "Write a JSON report to this path (default: <input stem>.dataguard.json "
            "in the current directory; the single character minus also means "
            "stdout)."
        ),
    )
    parser.add_argument(
        "--required-columns",
        help="Comma-separated column names that must be present, e.g. name,age.",
    )
    parser.add_argument(
        "--expected-types",
        help=(
            "Comma-separated type rules, e.g. age=int,score=number. "
            "Types: int, float, bool, date, datetime, string."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="DataGuard %s" % __version__,
    )
    return parser


def _default_json_path(csv_path: str) -> str:
    p = Path(csv_path)
    return str(p.parent / (p.stem + ".dataguard.json"))


def _write_text(path: str, text: str) -> None:
    target = Path(path)
    if target.exists() and not target.is_file():
        raise OSError("not a regular file: %s" % target)
    target.write_text(text, encoding="utf-8")


def _write_json(path: str, text: str) -> None:
    target = Path(path)
    if target.exists() and not target.is_file():
        raise OSError("not a regular file: %s" % target)
    target.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rows = load_csv(args.csv, args.encoding)
    except DataGuardError as exc:
        print("DataGuard: error: %s" % exc, file=sys.stderr)
        return 1

    result = profile_rows(rows)
    # Tell the pure profile engine where the input was and how it was read.
    result.path = args.csv
    result.encoding = args.encoding

    try:
        rules = apply_rules(result, args.required_columns, args.expected_types)
    except ValueError as exc:
        print("DataGuard: error: %s" % exc, file=sys.stderr)
        return 1
    result.rules = rules

    text_report = render_text(result)
    json_report = render_json(result)

    # Text report: None or the single character minus means "write to the
    # terminal"; a file path means write the report to that file. Both
    # destinations are guarded: a failure here is a runtime error (exit 1),
    # never a traceback, and never a partial overwrite of the input file.
    try:
        if args.report_text in (None, "-"):
            print(text_report)
        else:
            _write_text(args.report_text, text_report)

        if args.report_json == "-":
            print(json_report)
        elif args.report_json is None:
            _write_json(_default_json_path(args.csv), json_report)
        else:
            _write_json(args.report_json, json_report)
    except OSError as exc:
        print(f"DataGuard: error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    raise SystemExit(main())
