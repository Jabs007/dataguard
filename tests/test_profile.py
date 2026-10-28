from dataguard.errors import (
    EncodingError,
    EmptyFileError,
    InvalidPathError,
)
from dataguard.profile import (
    _analyze_column,
    _classify_cell,
    apply_rules,
    load_csv,
    profile_rows,
)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def test_load_csv_returns_header_and_rows():
    rows = load_csv("samples/clean.csv")
    assert rows[0] == ["name", "age", "city"]
    # header + 3 data rows; blank lines are dropped
    assert len(rows) == 4


def test_load_csv_drops_blank_lines():
    rows = load_csv("samples/constant.csv")
    assert len(rows) == 4  # header + 3 rows, no blank lines


def test_load_csv_missing_file_raises(monkeypatch, tmp_path, missing_csv):
    try:
        load_csv(str(missing_csv))
    except InvalidPathError:
        pass
    else:
        raise AssertionError("expected InvalidPathError for missing file")


def test_load_csv_non_regular_file_raises(tmp_path):
    # a directory is not a readable CSV
    try:
        load_csv(str(tmp_path))
    except InvalidPathError:
        pass
    else:
        raise AssertionError("expected InvalidPathError for a directory")


def test_load_csv_empty_file_raises(tmp_path, empty_csv):
    try:
        load_csv(empty_csv)
    except EmptyFileError:
        pass
    else:
        raise AssertionError("expected EmptyFileError for an empty file")


def test_load_csv_encoding_error(tmp_path):
    p = tmp_path / "binary.csv"
    p.write_bytes(b"\xff\xfe\x00\x01")
    try:
        load_csv(str(p))
    except EncodingError:
        pass
    else:
        raise AssertionError("expected EncodingError for undecodable bytes")


def test_classify_cell_detects_primitives():
    assert _classify_cell("30") == "int"
    assert _classify_cell("3.5") == "float"
    assert _classify_cell("true") == "bool"
    assert _classify_cell("2024-01-01") == "date"
    assert _classify_cell("2024-01-01 10:00") == "datetime"
    assert _classify_cell("hello") == "string"
    assert _classify_cell("   ") == "empty"
    assert _classify_cell("") == "empty"


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def test_profile_clean_csv_has_no_issues(clean_csv):
    rows = load_csv(clean_csv)
    result = profile_rows(rows)
    assert result.row_count == 2
    assert result.column_count == 3
    assert result.duplicate_row_count == 0
    assert result.duplicate_columns == []
    assert result.constant_columns == []
    assert result.total_missing == 0
    assert result.ragged_rows == 0


def test_profile_detects_duplicate_columns(dupheader_csv):
    rows = load_csv(dupheader_csv)
    result = profile_rows(rows)
    assert len(result.duplicate_columns) == 1
    assert result.duplicate_columns[0].name == "name"
    assert result.duplicate_columns[0].is_duplicate is True


def test_profile_detects_constant_column(constant_csv):
    rows = load_csv(constant_csv)
    result = profile_rows(rows)
    assert result.constant_columns == ["status"]
    status = result.columns[1]
    assert status.is_constant is True
    assert status.distinct_count == 1
    assert status.dtype == "string"


def test_profile_detects_missing_and_mixed_columns(messy_csv):
    rows = load_csv(messy_csv)
    result = profile_rows(rows)
    assert result.row_count == 5
    assert result.column_count == 4
    assert result.total_missing == 4
    assert result.ragged_rows == 1
    assert result.duplicate_row_count == 1

    score = result.columns[2]
    assert score.dtype == "mixed"
    assert score.suspicious == ["abc"]

    city = result.columns[3]
    assert city.is_constant is True


def test_profile_detects_duplicate_rows(messy_csv):
    rows = load_csv(messy_csv)
    result = profile_rows(rows)
    assert result.duplicate_row_count == 1


def test_profile_all_missing_column_is_flagged_separately(tmp_path):
    # A column that is entirely empty is NOT constant (nothing to compare to),
    # so it should appear in all_missing_columns instead.
    content = "a,b\n1,\n,\n"
    p = tmp_path / "allmissing.csv"
    p.write_text(content, encoding="utf-8")
    rows = load_csv(str(p))
    result = profile_rows(rows)
    assert result.all_missing_columns == ["b"]
    assert result.columns[1].is_constant is False


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

def test_apply_rules_required_column_present(clean_csv):
    rows = load_csv(clean_csv)
    result = profile_rows(rows)
    rules = apply_rules(result, "name,age", None)
    assert rules["required_columns"]["status"] == "ok"
    assert rules["required_columns"]["missing"] == []


def test_apply_rules_required_column_missing(clean_csv):
    rows = load_csv(clean_csv)
    result = profile_rows(rows)
    rules = apply_rules(result, "name,age,x", None)
    assert rules["required_columns"]["status"] == "failed"
    assert "x" in rules["required_columns"]["missing"]


def test_apply_rules_expected_type_violation(messy_csv):
    rows = load_csv(messy_csv)
    result = profile_rows(rows)
    rules = apply_rules(result, None, "score=int")
    assert rules["expected_types"]["status"] == "failed"
    check = rules["expected_types"]["checks"][0]
    assert check["column"] == "score"
    assert check["violating_cells"] == 1


def test_apply_rules_unknown_type_raises(messy_csv):
    rows = load_csv(messy_csv)
    result = profile_rows(rows)
    try:
        apply_rules(result, None, "score=currency")
    except ValueError as exc:
        assert "unknown type" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown type")
