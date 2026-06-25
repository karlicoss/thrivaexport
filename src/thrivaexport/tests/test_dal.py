from pathlib import Path

import pytest

from thrivaexport import dal


def test_dal_reads_sample_export(tmp_path: Path) -> None:
    source = Path("legacy/res.json")
    root = tmp_path / "export"
    root.mkdir()
    sample = source.read_text()
    (root / "20230601_TC7FC5XSW.json").write_text(sample)

    d = dal.DAL(root)

    exported_tests = list(d.tests())
    assert len(exported_tests) == 1
    test = exported_tests[0]
    assert test.id == "TC7FC5XSW"
    assert test.state == "complete"
    assert test.date == "2023-06-01"
    assert test.package_name == "Subscription test"

    results = list(test.analyte_results())
    assert len(results) == 20
    b12 = next(result for result in results if result.code == "B12")
    assert b12.name == "Total B12"
    assert b12.value == 533.0
    assert b12.unit == "pmol/L"
    assert b12.label == "normal"


def test_dal_requires_complete_test_files(tmp_path: Path) -> None:
    root = tmp_path / "export"
    root.mkdir()
    (root / "20230601_ACTIVE.json").write_text(
        '{"data": {"type": "test", "id": "ACTIVE", "attributes": {"state": "active"}}}'
    )

    with pytest.raises(AssertionError):
        dal.DAL(root)


def test_format_result_omits_unit_without_value() -> None:
    result = dal.AnalyteResult(
        raw={
            "id": "result",
            "type": "analyte_result",
            "attributes": {
                "analyte_id": "B12",
                "value": None,
                "unit": "pmol/L",
            },
        },
        analyte=None,
    )

    assert dal._format_result(result) == ""
