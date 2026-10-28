"""Edge-case tests for DataGuard (Checkpoint 3).

Covers: empty files, header-only files, blank lines, duplicate headers,
ragged rows, all-missing columns, mixed types, invalid rule tokens,
missing input files, unwritable report destinations, and that the input
file is never modified or overwritten.
"""

import json
from pathlib import Path

from dataguard.cli import main
from dataguard.profile import (
    apply_rules,
    load_csv,
    profile_rows,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _run_cli(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json_of(csv_path):
    # No Path.replace(): that method was removed in Python 3.12.
    return csv_path.rsplit(".csv", 1)[0] + ".dataguard.json"


# ---------------------------------------------------------------------------
# 1. Empty file
# ---------------------------------------------------------------------------

def test_empty_file_exits_1_and_graceful(tmp_path, capsys):
    p = _write(tmp_path, "empty.csv", "")
    code, out, err = _run_cli([p], capsys)
    assert code == 1
    assert "empty" in err


def test_empty_file_does_not_modify_input(tmp_path, capsys):
    p = _write(tmp_path, "empty.csv", "")
    before = Path(p).read_bytes()
    code = main([p])
    assert code == 1
    assert Path(p).read_bytes() == before  # input untouched on error


# ---------------------------------------------------------------------------
# 2. Header-only file
# ---------------------------------------------------------------------------

def test_header_only_file_exits_0(tmp_path, capsys):
    p = _write(tmp_path, "header_only.csv", "name,age,city\n")
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    assert "0 row(s) read" in out


# ---------------------------------------------------------------------------
# 3. Blank lines are ignored
# ---------------------------------------------------------------------------

def test_blank_lines_ignored(tmp_path, capsys):
    csv = (
        "name,age,city\n"
        "\n"
        "Alice,30,Nairobi\n"
        "\n"
        "\n"
        "Bob,25,Buenos Aires\n"
        "\n"
        "Carol,35,Oslo\n"
    )
    p = _write(tmp_path, "blanks.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    assert "3 row(s) read" in out


# ---------------------------------------------------------------------------
# 4. Duplicate headers
# ---------------------------------------------------------------------------

def test_duplicate_headers_detected(tmp_path, capsys):
    csv = "name,name,age\nA,1,30\nB,2,25\n"
    p = _write(tmp_path, "dup.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    assert "1 duplicate header name(s): name" in err or "1 duplicate header name(s): name" in out


# ---------------------------------------------------------------------------
# 5. Empty (all-missing) columns
# ---------------------------------------------------------------------------

def test_all_missing_column_is_not_constant(tmp_path):
    csv = "name,status\nAlice,\nBob,\n"
    p = _write(tmp_path, "allmissing.csv", csv)
    rows = load_csv(p)
    result = profile_rows(rows)
    assert result.all_missing_columns == ["status"]
    # zero non-missing values => not constant; the 'empty' dtype is the truth
    status_col = [c for c in result.columns if c.name == "status"][0]
    assert status_col.is_constant is False
    assert status_col.dtype == "empty"


# ---------------------------------------------------------------------------
# 6. Mixed types + suspicious values
# ---------------------------------------------------------------------------

def test_mixed_column_flags_suspicious_value(tmp_path):
    csv = "name,score\nAlice,88\nBob,95\nCarol,abc\n"
    p = _write(tmp_path, "mixed.csv", csv)
    rows = load_csv(p)
    result = profile_rows(rows)
    score = result.columns[1]
    assert score.dtype == "mixed"
    assert score.suspicious == ["abc"]


# ---------------------------------------------------------------------------
# 7. Ragged rows are counted and reported
# ---------------------------------------------------------------------------

def test_ragged_rows_counted(tmp_path, capsys):
    csv = (
        "name,age,city\n"
        "Alice,30,Nairobi\n"
        "Bob,25\n"
        "Carol,,,,,\n"
    )
    p = _write(tmp_path, "ragged.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    assert "2 row(s) have a different number of fields than the header (3)" in err or out
    json_path = _json_of(p)
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert data["summary"]["ragged_rows"] == 2


# ---------------------------------------------------------------------------
# 8. Invalid rule tokens -> runtime exit 1
# ---------------------------------------------------------------------------

def test_invalid_rule_token_exits_1(tmp_path, capsys):
    csv = "name,score\nAlice,88\nBob,abc\n"
    p = _write(tmp_path, "bad.csv", csv)
    code, out, err = _run_cli([p, "--expected-types", "score=currency"], capsys)
    assert code == 1
    assert "unknown type" in err


# ---------------------------------------------------------------------------
# 9. Missing input file -> exit 1
# ---------------------------------------------------------------------------

def test_missing_input_file_exits_1(tmp_path, capsys):
    code, out, err = _run_cli([str(tmp_path / "nope.csv")], capsys)
    assert code == 1
    assert "file not found" in err


# ---------------------------------------------------------------------------
# 10. Unwritable report destination -> exit 1
# ---------------------------------------------------------------------------

def test_unwritable_report_destination_exits_1(tmp_path, capsys):
    csv = "name,age\nAlice,30\n"
    p = _write(tmp_path, "ok.csv", csv)
    code, out, err = _run_cli([p, "-t", str(tmp_path / "no_such_dir" / "x.txt")], capsys)
    assert code == 1
    assert "not a regular file" in err or "unwritable" in err or "x.txt" in err


# ---------------------------------------------------------------------------
# 11. The input file is never modified or overwritten
# ---------------------------------------------------------------------------

def test_input_file_not_modified_or_overwritten(tmp_path):
    p = _write(tmp_path, "data.csv", "name,age\nAlice,30\n")
    before = Path(p).read_bytes()
    code = main([p])  # default JSON goes next to input
    assert code == 0
    assert Path(p).read_bytes() == before
    assert Path(p).parent / "data.dataguard.json"


# ---------------------------------------------------------------------------
# 12. Text and JSON agree on all substantive findings
# ---------------------------------------------------------------------------

def test_text_and_json_agree_on_duplicate_rows_and_missing(tmp_path, capsys):
    csv = "name,age,city\nAlice,30,Nairobi\nBob,25,\nAlice,30,Nairobi\n"
    p = _write(tmp_path, "agree.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    data = json.loads(Path(_json_of(p)).read_text(encoding="utf-8"))

    assert data["summary"]["duplicate_row_count"] == 1
    assert data["summary"]["total_missing_cells"] == 1
    assert data["summary"]["constant_column_count"] == 1  # city = Nairobi only
    assert "1 row(s) are exact duplicates" in out
    assert "1 missing cell(s)" in out


def test_text_and_json_agree_on_ragged_rows(tmp_path, capsys):
    csv = (
        "name,age,city\n"
        "Alice,30,Nairobi\n"
        "Bob,25\n"
        "Carol,,,,,\n"
    )
    p = _write(tmp_path, "ragged.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    data = json.loads(Path(_json_of(p)).read_text(encoding="utf-8"))

    assert data["summary"]["ragged_rows"] == 2
    assert "2 row(s) have a different number of fields" in out


def test_text_and_json_agree_on_duplicate_columns(tmp_path, capsys):
    csv = "name,name,age\nA,1,30\nB,2,25\n"
    p = _write(tmp_path, "dup.csv", csv)
    code, out, err = _run_cli([p], capsys)
    assert code == 0
    data = json.loads(Path(_json_of(p)).read_text(encoding="utf-8"))

    assert data["summary"]["duplicate_column_count"] == 1
    assert "1 duplicate header name(s)" in out


# ---------------------------------------------------------------------------
# Whitespace-only missing handling and rule-reporting gaps
# ---------------------------------------------------------------------------

def test_whitespace_only_cell_is_treated_as_missing(tmp_path):
    # Three data rows: two are whitespace-only, one has content.
    csv = "v\n \n \t \n x \n"
    p = _write(tmp_path, "ws.csv", csv)
    rows = load_csv(p)
    result = profile_rows(rows)
    col = result.columns[0]
    # Empty / whitespace-only cells count as missing; the non-missing cell is
    # a single string value, so the column is constant (nothing missing to
    # break the value).
    assert col.missing_count == 2
    assert col.dtype == "string"
    assert col.distinct_count == 1
    assert col.is_constant is True


def test_expected_type_skipped_column_is_shown_in_text_report(tmp_path, capsys):
    # A mistyped column name must never be silent: it should appear in the text
    # report as "skipped", even though overall status stays "ok".
    csv = "name,score\nAlice,88\n"
    p = _write(tmp_path, "skipped.csv", csv)
    code, out, err = _run_cli([p, "--expected-types", "score=int,szz=int"], capsys)
    assert code == 0
    assert "szz" in out, "typo'd expected-type column was invisible in text report"
    data = json.loads(Path(_json_of(p)).read_text(encoding="utf-8"))
    skipped = [c for c in data["rules"]["expected_types"]["checks"] if c["status"] == "skipped"]
    assert len(skipped) == 1
    assert skipped[0]["column"] == "szz"
    assert skipped[0]["status"] == "skipped"
