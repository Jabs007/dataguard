import json
from pathlib import Path

import pytest

from dataguard.cli import main


def json_file_of(csv_path):
    return Path(csv_path).parent / (Path(csv_path).stem + ".dataguard.json")


def test_cli_success_writes_json_next_to_input(tmp_path, clean_csv, capsys):
    code = main([clean_csv])
    out = capsys.readouterr()
    assert code == 0
    assert out.out.startswith("DataGuard")
    assert "Columns" in out.out

    json_file = json_file_of(clean_csv)
    assert json_file.exists()
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["row_count"] == 2
    assert data["summary"]["total_columns"] == 3
    assert data["summary"]["duplicate_row_count"] == 0


def test_cli_text_report_goes_to_terminal_by_default(tmp_path, clean_csv, capsys):
    code = main([clean_csv])
    out = capsys.readouterr()
    assert code == 0
    assert "Input file" in out.out
    assert "Encoding" in out.out


def test_cli_report_json_flag_writes_json_to_path(tmp_path, clean_csv, capsys):
    out_path = tmp_path / "custom.json"
    code = main([clean_csv, "-j", str(out_path)])
    out = capsys.readouterr()
    assert code == 0
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8"))["row_count"] == 2


def test_cli_report_json_minus_writes_json_to_terminal(tmp_path, clean_csv, capsys):
    code = main([clean_csv, "-j", "-"])
    out = capsys.readouterr()
    assert code == 0
    assert "DataGuard" in out.out
    assert out.out.count("{") >= 1


def test_cli_report_text_flag_writes_to_file(tmp_path, clean_csv, capsys):
    txt_path = tmp_path / "report.txt"
    code = main([clean_csv, "-t", str(txt_path)])
    out = capsys.readouterr()
    assert code == 0
    assert txt_path.exists()
    assert "Input file" in txt_path.read_text(encoding="utf-8")


def test_cli_report_text_minus_goes_to_terminal(tmp_path, clean_csv, capsys):
    code = main([clean_csv, "-t", "-"])
    out = capsys.readouterr()
    assert code == 0
    assert "Input file" in out.out


def test_cli_missing_file_exits_1(tmp_path, capsys):
    code = main([str(tmp_path / "nope.csv")])
    assert code == 1
    assert "file not found" in capsys.readouterr().err


def test_cli_no_args_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_cli_invalid_flag_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--bogus"])
    assert exc.value.code == 2


def test_cli_required_columns_rule_ok(tmp_path, clean_csv, capsys):
    code = main([clean_csv, "--required-columns", "name"])
    out = capsys.readouterr()
    assert code == 0
    data = json.loads(json_file_of(clean_csv).read_text(encoding="utf-8"))
    assert data["rules"]["required_columns"]["status"] == "ok"
    assert data["rules"]["required_columns"]["missing"] == []


def test_cli_required_column_missing(tmp_path, clean_csv, capsys):
    code = main([clean_csv, "--required-columns", "name,age,x"])
    out = capsys.readouterr()
    assert code == 0
    data = json.loads(json_file_of(clean_csv).read_text(encoding="utf-8"))
    assert data["rules"]["required_columns"]["status"] == "failed"
    assert "x" in data["rules"]["required_columns"]["missing"]


def test_cli_expected_type_rule_failed(messy_csv, capsys):
    code = main([messy_csv, "--expected-types", "score=int"])
    out = capsys.readouterr()
    assert code == 0
    data = json.loads(json_file_of(messy_csv).read_text(encoding="utf-8"))
    assert data["rules"]["expected_types"]["status"] == "failed"
    assert data["rules"]["expected_types"]["checks"][0]["column"] == "score"
    assert data["rules"]["expected_types"]["checks"][0]["violating_cells"] == 1
