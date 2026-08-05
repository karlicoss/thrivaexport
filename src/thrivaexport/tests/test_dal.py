from pathlib import Path

import pytest

from thrivaexport import dal


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
