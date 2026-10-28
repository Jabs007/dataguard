import pytest

CLEAN_CSV = """name,age,city
Alice,30,Nairobi
Bob,25,Buenos Aires
"""

MESSY_CSV = """name,age,score,city
Alice,30,88,Nairobi
Bob,25,95,
Alice,30,88,Nairobi
Carol,,
Bob, 25 ,abc,Nairobi
"""

CONSTANT_CSV = """name,status
Alice,active
Bob,active
Carol,active
"""

DUPHEADER_CSV = """name,name,age
A,1,30
B,2,25
C,3,35
"""


@pytest.fixture
def clean_csv(tmp_path):
    p = tmp_path / "clean.csv"
    p.write_text(CLEAN_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def messy_csv(tmp_path):
    p = tmp_path / "messy.csv"
    p.write_text(MESSY_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def constant_csv(tmp_path):
    p = tmp_path / "constant.csv"
    p.write_text(CONSTANT_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def dupheader_csv(tmp_path):
    p = tmp_path / "dupheader.csv"
    p.write_text(DUPHEADER_CSV, encoding="utf-8")
    return str(p)


@pytest.fixture
def empty_csv(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    return str(p)


@pytest.fixture
def missing_csv(tmp_path):
    return str(tmp_path / "does_not_exist.csv")


def json_path_of(csv_path):
    return csv_path.rsplit(".csv", 1)[0] + ".dataguard.json"
