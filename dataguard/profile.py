"""Core CSV loading and data-quality profiling engine.

This module has no dependency on the command-line interface and no third-party
library. It is deliberately side-effect free so it can be unit-tested in
isolation.

Design notes
------------
* CSV rows are read with the stdlib :mod:`csv` module into lists of strings.
  We deliberately use lists (instead of :class:`csv.DictReader`) because a
  :class:`csv.DictReader` silently renumbers duplicate headers, which would
  hide duplicate column names. By inspecting the header as a list first we
  detect duplicate names *before* rows are turned into dictionaries, so no
  data can be lost.
* A "missing" cell is one that is empty or contains only whitespace.
  Values such as "NA" / "NULL" / "N/A" are **not** treated as missing
  unless the user adds an explicit configuration option (out of scope for v1).
* Type inference is deliberately conservative. A column is reported as a
  single primitive type only when every non-missing cell agrees. Otherwise it
  is reported as "mixed" and the individual values that disagree are listed as
  suspicious examples rather than failing the whole file.
"""

from __future__ import annotations

import csv
import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

from .errors import (
    DataGuardError,
    EncodingError,
    EmptyFileError,
    InvalidPathError,
    MalformedCSVError,
)

# A column is "constant" when all of its non-missing cells share one value.
# Missing cells (empty or whitespace only) are ignored for that check.
TYPE_UNION = {"int", "float", "bool", "date", "datetime", "string"}

_DEFAULT_DELIMITER = ","


@dataclass
class ColumnResult:
    """One profiled column.

    ``non_missing`` is used internally by the validation rules; it is not
    part of the report schema and must not be serialised.
    """

    name: str
    index: int
    dtype: str
    missing_count: int
    missing_pct: float
    distinct_count: int
    is_constant: bool
    is_duplicate: bool
    suspicious: list[str]
    examples: list[str]
    non_missing: list[str] = field(default_factory=list, repr=False)


@dataclass
class ProfileResult:
    path: str
    encoding: str
    delimiter: str
    row_count: int
    column_count: int
    columns: list[ColumnResult]
    duplicate_columns: list[ColumnResult] = field(default_factory=list)
    duplicate_row_count: int = 0
    duplicate_row_examples: list[str] = field(default_factory=list)
    constant_columns: list[str] = field(default_factory=list)
    all_missing_columns: list[str] = field(default_factory=list)
    ragged_rows: int = 0
    total_missing: int = 0
    missing_by_column: dict[str, int] = field(default_factory=dict)
    dataset_issues: list[str] = field(default_factory=list)
    checks: dict[str, object] = field(default_factory=dict)
    rules: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_csv(path, encoding: str = "utf-8-sig", newline: str = "") -> list[list[str]]:
    """Read ``path`` as text and return a list of CSV rows (each a list of cells).

    A fully blank line (no fields) is treated as a blank line and ignored, so
    trailing newlines never produce a phantom row. Blank lines inside the file
    are also skipped, which keeps the engine deterministic.

    Raises
    ------
    InvalidPathError
        If the path does not exist or is not a regular file.
    EncodingError
        If the file cannot be decoded with the given encoding.
    EmptyFileError
        If the file contains no header row at all.
    """
    path = Path(path)
    if not path.exists():
        raise InvalidPathError(f"file not found: {path}")
    if not path.is_file():
        raise InvalidPathError(f"not a regular file: {path}")

    try:
        with path.open("r", encoding=encoding, newline=newline) as handle:
            rows = list(csv.reader(handle))
    except UnicodeDecodeError as exc:
        raise EncodingError(
            f"could not decode {path} with encoding {encoding!r}: {exc}"
        ) from exc

    rows = [row for row in rows if row]  # drop blank lines
    if not rows:
        raise EmptyFileError(f"file is empty (no header row): {path}")
    return rows


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def _has_time(text: str) -> bool:
    try:
        value = _dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return bool(value.hour or value.minute or value.second or value.microsecond)


def _classify_cell(text: str) -> str:
    """Return the primitive type name of one cell.

    Order matters: booleans are checked before integers so that "true" is not
    mistaken for the integer 1, and date/time forms are checked before plain
    numerics so that "2024-01-01" is not reported as an integer.
    """
    stripped = text.strip()
    if not stripped:
        return "empty"
    lowered = stripped.lower()
    if lowered in {"true", "false", "yes", "no", "y", "n"}:
        return "bool"
    # date/time: fromisoformat accepts 'T' and space separators in Python 3.11+
    # (unlike date.fromisoformat, which rejects times). A time part makes the
    # column 'datetime', otherwise the cell is a plain 'date'.
    try:
        value = _dt.datetime.fromisoformat(stripped)
    except ValueError:
        value = None
    if value is not None:
        if value.hour or value.minute or value.second or value.microsecond:
            return "datetime"
        return "date"
    try:
        int(stripped)
        return "int"
    except ValueError:
        pass
    try:
        float(stripped)
        return "float"
    except ValueError:
        pass
    return "string"


# ---------------------------------------------------------------------------
# Column analysis
# ---------------------------------------------------------------------------

def _analyze_column(name: str, index: int, cells: list[str]) -> ColumnResult:
    """Inspect one column and summarise its quality and inferred type."""
    non_missing = [cell for cell in cells if cell.strip() != ""]
    total = len(cells)
    missing_count = total - len(non_missing)
    missing_pct = (missing_count / total * 100.0) if total else 0.0
    distinct = len(set(non_missing))

    if non_missing:
        counts: dict[str, int] = {}
        for cell in non_missing:
            counts[_classify_cell(cell)] = counts.get(_classify_cell(cell), 0) + 1

        if len(counts) == 1:
            dtype = next(iter(counts))
            suspicious: list[str] = []
        else:
            # Mixed column: report the majority type and list disagreeing
            # values as suspicious examples (capped at 8).
            dtype = "mixed"
            majority_type = max(counts, key=counts.get)
            suspicious = []
            seen: set[str] = set()
            for cell in non_missing:
                if _classify_cell(cell) != majority_type and cell not in seen:
                    suspicious.append(cell)
                    seen.add(cell)
                if len(suspicious) >= 8:
                    break
    else:
        dtype, suspicious = "empty", []

    # Constant means exactly one distinct non-missing value. A column that is
    # entirely missing has zero distinct values and is flagged separately.
    is_constant = len(set(non_missing)) == 1

    return ColumnResult(
        name=name,
        index=index,
        dtype=dtype,
        missing_count=missing_count,
        missing_pct=missing_pct,
        distinct_count=distinct,
        is_constant=is_constant,
        is_duplicate=False,
        suspicious=suspicious,
        examples=list(dict.fromkeys(non_missing))[:3],
        non_missing=non_missing,
    )


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def profile_rows(rows: list[list[str]]) -> ProfileResult:
    """Turn raw CSV rows into a :class:`ProfileResult` (no I/O, no print)."""
    if not rows:
        raise EmptyFileError("CSV has no header row.")

    header = rows[0]
    data_rows = rows[1:]
    column_count = len(header)

    # 1) Duplicate headers must be found *before* any dictionary conversion.
    seen_indices: set[str] = set()
    duplicate_columns: list[ColumnResult] = []
    for index, name in enumerate(header):
        if name in seen_indices:
            duplicate_columns.append(
                ColumnResult(
                    name=name,
                    index=index,
                    dtype="string",
                    missing_count=0,
                    missing_pct=0.0,
                    distinct_count=0,
                    is_constant=False,
                    is_duplicate=True,
                    suspicious=[],
                    examples=[],
                )
            )
        else:
            seen_indices.add(name)

    # 2) Per-column analysis. Ragged rows (wrong number of fields) are counted
    #    globally and the missing tail of a row is treated as missing cells.
    columns: list[ColumnResult] = []
    for index, name in enumerate(header):
        cells = [row[index] if index < len(row) else "" for row in data_rows]
        columns.append(_analyze_column(name, index, cells))

    missing_by_column = {col.name: col.missing_count for col in columns}
    total_missing = sum(missing_by_column.values())

    # 3) Duplicate full rows.
    seen: set[tuple[str, ...]] = set()
    duplicate_row_count = 0
    duplicate_row_examples: list[str] = []
    for row in data_rows:
        key = tuple(row)
        if key in seen:
            duplicate_row_count += 1
            if len(duplicate_row_examples) < 5:
                duplicate_row_examples.append(",".join(key))
        else:
            seen.add(key)

    # 4) Ragged rows.
    ragged_rows = sum(1 for row in data_rows if len(row) != column_count)

    # 5) Constant columns and all-missing columns.
    constant_columns = [c.name for c in columns if c.is_constant]
    all_missing_columns = [
        c.name for c in columns if data_rows and c.missing_count == len(data_rows)
    ]

    # 6) Human-readable issue list.
    issues: list[str] = []
    if duplicate_row_count:
        issues.append(f"{duplicate_row_count} row(s) are exact duplicates of an earlier row.")
    if ragged_rows:
        issues.append(
            f"{ragged_rows} row(s) have a different number of fields than the header ({column_count})."
        )
    columns_with_missing = [c.name for c in columns if c.missing_count]
    if columns_with_missing:
        issues.append(
            f"{total_missing} missing cell(s) across {len(columns_with_missing)} column(s): "
            f"{', '.join(columns_with_missing)}."
        )
    if constant_columns:
        issues.append(f"{len(constant_columns)} constant column(s): {', '.join(constant_columns)}.")
    if all_missing_columns:
        issues.append(f"All-missing column(s): {', '.join(all_missing_columns)}.")
    if duplicate_columns:
        issues.append(f"{len(duplicate_columns)} duplicate header name(s): "
                      f"{', '.join(c.name for c in duplicate_columns)}.")

    mixed_columns = [c.name for c in columns if c.dtype == "mixed"]
    if mixed_columns:
        issues.append(f"{len(mixed_columns)} column(s) have mixed or ambiguous types: "
                      f"{', '.join(mixed_columns)}.")

    # 7) Structured "checks" block (shared by text and JSON reports).
    checks = {
        "row_count": {
            "status": "ok",
            "message": f"{len(data_rows)} row(s) read.",
            "row_count": len(data_rows),
        },
        "columns": {
            "status": "ok",
            "message": f"{len(header)} column(s) found.",
            "column_count": len(header),
        },
        "missing_values": {
            "status": "ok" if total_missing == 0 else "warning",
            "message": (
                f"{total_missing} missing cell(s) across {len(columns_with_missing)} column(s)."
                if columns_with_missing
                else "no missing values."
            ),
            "total_missing_cells": total_missing,
            "columns_with_missing": len(columns_with_missing),
            "missing_by_column": missing_by_column,
        },
        "duplicate_rows": {
            "status": "ok" if duplicate_row_count == 0 else "warning",
            "message": (
                f"{duplicate_row_count} duplicate row(s) found."
                if duplicate_row_count
                else "no duplicate rows."
            ),
            "duplicate_row_count": duplicate_row_count,
            "example_rows": duplicate_row_examples,
        },
        "duplicate_columns": {
            "status": "ok" if not duplicate_columns else "warning",
            "message": f"{len(duplicate_columns)} duplicate header name(s).",
            "duplicate_columns": [
                {"name": c.name, "index": c.index} for c in duplicate_columns
            ],
        },
        "constant_columns": {
            "status": "ok" if not constant_columns else "warning",
            "message": f"{len(constant_columns)} constant column(s).",
            "constant_columns": constant_columns,
        },
        "type_inference": {
            "status": "ok" if not mixed_columns else "warning",
            "message": (
                f"{len(mixed_columns)} column(s) have mixed or ambiguous types."
                if mixed_columns
                else "all columns inferred a single type."
            ),
            "columns_with_mixed_type": len(mixed_columns),
            "columns": [
                {"name": c.name, "dtype": c.dtype, "suspicious": c.suspicious}
                for c in columns
                if c.dtype == "mixed"
            ],
        },
    }

    return ProfileResult(
        path="",
        encoding="",
        delimiter=",",
        row_count=len(data_rows),
        column_count=len(header),
        columns=columns,
        duplicate_columns=duplicate_columns,
        duplicate_row_count=duplicate_row_count,
        duplicate_row_examples=duplicate_row_examples,
        constant_columns=constant_columns,
        all_missing_columns=all_missing_columns,
        ragged_rows=ragged_rows,
        total_missing=total_missing,
        missing_by_column=missing_by_column,
        dataset_issues=issues,
        checks=checks,
        rules={},
    )


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def parse_expected_types(spec: str) -> dict[str, str]:
    """Parse ``column=type,column=type`` into a mapping.

    Types are one of: int, float, bool, date, datetime, string.
    """
    rules: dict[str, str] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                f"expected-type rule is not 'column=type': {item!r}"
            )
        column, type_name = item.split("=", 1)
        column = column.strip()
        type_name = type_name.strip().lower()
        if type_name not in TYPE_UNION:
            raise ValueError(
                f"unknown type {type_name!r} for column {column!r}; "
                f"expected one of {sorted(TYPE_UNION)}"
            )
        rules[column] = type_name
    return rules


def apply_rules(
    result: ProfileResult,
    required_columns: str | None = None,
    expected_types: str | None = None,
) -> dict[str, object]:
    """Apply required-column and expected-type rules to a profiling result."""
    rules: dict[str, object] = {
        "status": "ok",
        "required_columns": {},
        "expected_types": {"checks": [], "status": "ok"},
    }

    header_names = [c.name for c in result.columns]
    header_set = set(header_names)

    required = [c for c in (required_columns or "").split(",") if c.strip()]
    missing_required = [c for c in required if c not in header_set]
    rules["required_columns"] = {
        "status": "ok" if not missing_required else "failed",
        "required": required,
        "present": [c for c in required if c in header_set],
        "missing": missing_required,
    }

    expected: dict[str, str] = {}
    if expected_types:
        expected = parse_expected_types(expected_types)

    checks: list[dict[str, object]] = []
    for column, type_name in expected.items():
        match = next((c for c in result.columns if c.name == column), None)
        if match is None:
            checks.append(
                {
                    "column": column,
                    "expected_type": type_name,
                    "status": "skipped",
                    "reason": "column not found in header",
                }
            )
            continue
        violations = sum(
            1 for cell in match.non_missing if _classify_cell(cell) != type_name
        )
        status = "ok" if violations == 0 else "failed"
        checks.append(
            {
                "column": column,
                "expected_type": type_name,
                "violating_cells": violations,
                "status": status,
            }
        )

    rules["expected_types"] = {
        "checks": checks,
        "status": "ok" if all(c["status"] != "failed" for c in checks) else "failed",
    }
    rules["status"] = (
        "failed"
        if rules["required_columns"]["status"] == "failed"
        or rules["expected_types"]["status"] == "failed"
        else "ok"
    )
    return rules
