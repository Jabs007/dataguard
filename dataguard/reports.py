"""Text and JSON report rendering.

Both renderers consume the same :class:`ProfileResult`, so the text report and
the JSON report always describe the same findings. The JSON schema is
documented in the README.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .profile import ProfileResult

# Stable, documented JSON top-level keys.
JSON_TOP = [
    "tool",
    "version",
    "generated_at",
    "input_file",
    "encoding",
    "delimiter",
    "row_count",
    "column_count",
    "checks",
    "rules",
    "columns",
    "dataset_issues",
    "summary",
]


def _summarise(result: ProfileResult) -> dict[str, object]:
    return {
        "total_columns": result.column_count,
        "columns_with_missing": sum(1 for c in result.columns if c.missing_count),
        "duplicate_row_count": result.duplicate_row_count,
        "duplicate_column_count": len(result.duplicate_columns),
        "constant_column_count": len(result.constant_columns),
        "ragged_rows": result.ragged_rows,
        "mixed_type_columns": sum(1 for c in result.columns if c.dtype == "mixed"),
        "total_missing_cells": result.total_missing,
    }


def build_json_payload(result: ProfileResult) -> dict[str, object]:
    """Build the exact dictionary that is serialised to JSON."""
    return {
        "tool": "DataGuard",
        "version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": result.path,
        "encoding": result.encoding,
        "delimiter": result.delimiter,
        "row_count": result.row_count,
        "column_count": result.column_count,
        "checks": result.checks,
        "rules": result.rules,
        "columns": [
            {
                "name": c.name,
                "index": c.index,
                "dtype": c.dtype,
                "missing_count": c.missing_count,
                "missing_pct": c.missing_pct,
                "distinct_count": c.distinct_count,
                "is_constant": c.is_constant,
                "is_duplicate": c.is_duplicate,
                "suspicious": c.suspicious,
                "examples": c.examples,
            }
            for c in result.columns
        ],
        "dataset_issues": result.dataset_issues,
        "summary": _summarise(result),
    }


def render_json(result: ProfileResult) -> str:
    """Return a deterministic JSON report as a string."""
    payload = build_json_payload(result)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_text(result: ProfileResult) -> str:
    """Return a human-readable, stable text report."""
    lines: list[str] = []
    lines.append("DataGuard — CSV data-quality report")
    lines.append("=" * 46)
    lines.append(f"Input file : {result.path}")
    lines.append(f"Encoding   : {result.encoding}")
    lines.append(f"Delimiter  : {result.delimiter}")
    lines.append(f"Rows       : {result.row_count}")
    lines.append(f"Columns    : {result.column_count}")
    lines.append("")
    lines.append("Summary")
    lines.append("-" * 46)
    lines.append(f"  Duplicate rows            : {result.duplicate_row_count}")
    lines.append(f"  Duplicate columns         : {len(result.duplicate_columns)}")
    lines.append(f"  Constant columns          : {len(result.constant_columns)}")
    lines.append(f"  All-missing columns       : {len(result.all_missing_columns)}")
    lines.append(f"  Columns with missing      : {sum(1 for c in result.columns if c.missing_count)}")
    lines.append(f"  Columns with mixed type   : {sum(1 for c in result.columns if c.dtype == 'mixed')}")
    lines.append(f"  Total missing cells       : {result.total_missing}")
    lines.append("")
    lines.append("Columns")
    lines.append("-" * 46)
    header = f"{'Name':<22}{'Idx':>4}{'Type':<10}{'Missing':>9}{'Dist':>6}  Const  Dupd  Sample"
    lines.append(header)
    lines.append("-" * 46)
    for c in result.columns:
        const = "yes" if c.is_constant else "-"
        dup = "yes" if c.is_duplicate else "-"
        sample = ",".join(c.examples[:3]) if c.examples else "-"
        lines.append(
            f"{c.name:<22}{c.index:>4}{c.dtype:<10}{c.missing_count:>9}"
            f"{c.distinct_count:>6}  {const:>5}  {dup:>5}  {sample}"
        )
    lines.append("")

    if result.dataset_issues:
        lines.append("Dataset issues")
        lines.append("-" * 46)
        for issue in result.dataset_issues:
            lines.append(f"  - {issue}")
        lines.append("")

    lines.append("Checks")

    # Rules (required columns + expected types) are reported separately so the
    # text and JSON reports expose the same findings.
    rules = result.rules
    if rules:
        lines.append("Rules")
        lines.append("-" * 46)
        req = rules.get("required_columns", {})
        lines.append(f"  required_columns : {req.get('status')}")
        for col in req.get("missing", []):
            lines.append(f"    missing required column: {col}")
        exp = rules.get("expected_types", {})
        lines.append(f"  expected_types   : {exp.get('status')}")
        for check in exp.get("checks", []):
            c = check.get("column", "?")
            ctype = check.get("expected_type", "?")
            cnt = int(check.get("violating_cells", 0))
            st = check.get("status", "ok")
            lines.append(
                f"    {c:<24} expected {ctype:<8} {st:<8} {cnt} violating cell(s)"
            )
        if not exp.get("checks"):
            lines.append("    (none)")
        lines.append("")
    lines.append("-" * 46)
    for name, check in result.checks.items():
        status = check.get("status", "?")
        message = check.get("message", "")
        lines.append(f"  {name:<22} {status:<8} {message}")
    return "\n".join(lines)
