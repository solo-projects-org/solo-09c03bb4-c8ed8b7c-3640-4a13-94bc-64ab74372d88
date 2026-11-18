"""CSV 解析、去重、冲突与覆盖范围校验的单元测试。"""

import pytest

from app.csv_import import CsvImportError, build_crosstab, parse_tests


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_parse_ok_and_dedup():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,是\n"
        "A001,内科,W1,是\n"      # 同号同内容：只计一次
        "A002,内科,W1,否\n"
        "A003,外科,W2,阳性\n"
        "A004,外科,W2,0\n"
    )
    records = parse_tests(data)
    assert len(records) == 4
    ids = [r.test_id for r in records]
    assert ids.count("A001") == 1


def test_conflict_rejected():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,是\n"
        "A001,外科,W1,是\n"      # 同号不同病区 -> 冲突
    )
    with pytest.raises(CsvImportError) as ei:
        parse_tests(data)
    assert any("冲突" in e for e in ei.value.errors)


def test_conflict_positive_flag_rejected():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,是\n"
        "A001,内科,W1,否\n"      # 同号不同阴阳性 -> 冲突
    )
    with pytest.raises(CsvImportError):
        parse_tests(data)


def test_missing_column_rejected():
    data = csv_bytes("检验号,病区,是否阳性\nA001,内科,是\n")
    with pytest.raises(CsvImportError) as ei:
        parse_tests(data)
    assert any("周次" in e for e in ei.value.errors)


def test_ward_coverage_validation():
    one_ward = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,是\n"
        "A002,内科,W2,否\n"
    )
    with pytest.raises(CsvImportError) as ei:
        parse_tests(one_ward)
    assert any("病区" in e for e in ei.value.errors)

    four_weeks = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        + "".join(f"A{i:03d},内科,W{i},是\n" for i in range(1, 5))
        + "B001,外科,W1,否\n"
    )
    with pytest.raises(CsvImportError) as ei:
        parse_tests(four_weeks)
    assert any("周次" in e for e in ei.value.errors)


def test_bad_positive_value_rejected():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,也许\n"
        "A002,外科,W2,是\n"
    )
    with pytest.raises(CsvImportError) as ei:
        parse_tests(data)
    assert any("是否阳性" in e for e in ei.value.errors)


def test_empty_file_rejected():
    with pytest.raises(CsvImportError):
        parse_tests(b"")


def test_bom_and_positive_variants():
    data = "﻿检验号,病区,周次,是否阳性\nA001,内科,W1,TRUE\nA002,外科,W2,y\nA003,外科,W2,n\n".encode("utf-8")
    records = parse_tests(data)
    pos = {r.test_id: r.positive for r in records}
    assert pos == {"A001": True, "A002": True, "A003": False}


def test_crosstab_counts_positive_only():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,W1,是\n"
        "A002,内科,W1,否\n"
        "A003,内科,W2,是\n"
        "A004,外科,W1,否\n"      # 外科 W1 仅阴性 -> 0
        "A005,外科,W2,是\n"
    )
    records = parse_tests(data)
    wards, weeks, counts = build_crosstab(records)
    assert wards == ["内科", "外科"]
    assert weeks == ["W1", "W2"]
    assert counts == [[1, 1], [0, 1]]


def test_numeric_week_sorting():
    data = csv_bytes(
        "检验号,病区,周次,是否阳性\n"
        "A001,内科,10,是\n"
        "A002,内科,9,是\n"
        "A003,外科,9,否\n"
    )
    records = parse_tests(data)
    _, weeks, _ = build_crosstab(records)
    assert weeks == ["9", "10"]
