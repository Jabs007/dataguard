import json

from dataguard.profile import load_csv, profile_rows
from dataguard.reports import render_json, render_text


def _result(clean_csv):
    return profile_rows(load_csv(clean_csv))


def test_json_report_is_valid_and_stable_structure(clean_csv):
    result = _result(clean_csv)
    data = json.loads(render_json(result))

    top_keys = {
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
    }
    assert set(data.keys()) == top_keys
    assert data["row_count"] == 2
    assert data["column_count"] == 3
    assert data["summary"]["duplicate_row_count"] == 0
    assert data["columns"][0]["name"] == "name"
    assert data["columns"][0]["dtype"] == "string"


def test_json_and_text_have_same_summary(clean_csv):
    result = _result(clean_csv)
    text = render_text(result)
    data = json.loads(render_json(result))

    assert data["summary"]["total_columns"] == result.column_count
    assert data["summary"]["duplicate_row_count"] == result.duplicate_row_count
    assert data["summary"]["constant_column_count"] == len(result.constant_columns)
    assert data["summary"]["mixed_type_columns"] == 0
    assert "2 row(s) read" in text


def test_text_report_contains_key_findings(messy_csv):
    result = profile_rows(load_csv(messy_csv))
    text = render_text(result)
    assert "5 row(s) read" in text
    assert "1 duplicate row(s) found" in text
    assert "1 constant column(s)" in text
    assert "1 column(s) have mixed or ambiguous types" in text
    assert "score" in text


def test_text_report_lists_every_column():
    result = profile_rows(load_csv("samples/constant.csv"))
    text = render_text(result)
    # Every column appears with its inferred type and sample value.
    assert "status" in text
    assert "active" in text
