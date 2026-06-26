from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from thrivaexport import export


class FakeResponse:
    def __init__(self, value: Any, *, status_code: int = 200) -> None:
        self.value = value
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        return self.value

    def raise_for_status(self) -> None:
        return None


def test_test_file_name_uses_stable_date_and_id() -> None:
    assert (
        export._test_file_name(
            {
                "id": "TC7FC5XSW",
                "type": "test",
                "attributes": {"test_date": "2023-06-01"},
            }
        )
        == "20230601_TC7FC5XSW.json"
    )


def test_list_tests_follows_links(monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)
    get_json = Mock(
        side_effect=[
            {
                "data": [{"type": "test", "id": "a"}],
                "links": {"next": "https://api.thriva.co/v1/tests?page=2"},
            },
            {
                "data": [{"type": "test", "id": "b"}],
            },
        ]
    )
    monkeypatch.setattr(
        client,
        "get_json",
        get_json,
    )

    result = client.list_tests(limit=1)

    assert result == {
        "data": [
            {"type": "test", "id": "a"},
            {"type": "test", "id": "b"},
        ],
    }
    get_json.assert_any_call(
        "/tests",
        params={
            "filter[state]": "complete",
            "limit": 1,
            "offset": 0,
        },
    )


def test_list_tests_follows_offset_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)
    get_json = Mock(
        side_effect=[
            {
                "data": [
                    {"type": "test", "id": "a"},
                    {"type": "test", "id": "b"},
                ],
                "meta": {"pagination": {"limit": 2, "offset": 0, "total_count": 3}},
            },
            {
                "data": [{"type": "test", "id": "c"}],
                "meta": {"pagination": {"limit": 2, "offset": 2, "total_count": 3}},
            },
        ]
    )
    monkeypatch.setattr(client, "get_json", get_json)

    result = client.list_tests(limit=2)

    assert result == {
        "data": [
            {"type": "test", "id": "a"},
            {"type": "test", "id": "b"},
            {"type": "test", "id": "c"},
        ],
    }
    get_json.assert_any_call(
        "/tests",
        params={
            "filter[state]": "complete",
            "limit": 2,
            "offset": 2,
        },
    )


def test_authenticate_verifies_self(monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)
    request = Mock(return_value=FakeResponse({"location": "/tests"}))
    get_json = Mock(return_value={"data": {"type": "user", "id": "user"}})
    monkeypatch.setattr(client, "request", request)
    monkeypatch.setattr(client, "get_json", get_json)

    assert client.authenticate(email="me@example.com", password="secret") == {"data": {"type": "user", "id": "user"}}
    request.assert_called_once()
    kwargs = request.call_args.kwargs
    assert kwargs["json"] == {
        "grant_type": "password",
        "type": "user",
        "username": "me@example.com",
        "password": "secret",
    }
    get_json.assert_called_once_with(
        "/self",
        params={"include": "user_preference"},
    )


def test_get_test_discovers_include_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)

    def get_json(endpoint: str, *, params: dict[str, str | int] | None = None) -> dict[str, Any]:
        assert endpoint == "/tests/test"
        if params is None:
            return {
                "data": {
                    "type": "test",
                    "id": "test",
                    "relationships": {
                        "report": {"data": {"type": "report", "id": "report"}},
                        "result": {"data": {"type": "test_result", "id": "result"}},
                    },
                }
            }
        include = params["include"]
        assert isinstance(include, str), include
        if include == "report":
            return {"included": []}
        if include == "result":
            return {
                "included": [
                    {
                        "type": "test_result",
                        "id": "result",
                        "relationships": {
                            "analyte_results": {"data": []},
                        },
                    }
                ]
            }
        if include == "result.analyte_results":
            return {"included": [{"type": "analyte_result", "id": "result_B12"}]}
        assert include == "report,result,result.analyte_results", include
        return {"data": {"type": "test", "id": "test"}, "included": []}

    monkeypatch.setattr(client, "get_json", Mock(side_effect=get_json))

    assert client.get_test("test") == {"data": {"type": "test", "id": "test"}, "included": []}


def test_export_account_skips_existing_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)
    monkeypatch.setattr(
        client,
        "list_tests",
        Mock(
            return_value={
                "data": [
                    {
                        "type": "test",
                        "id": "TC7FC5XSW",
                        "attributes": {"test_date": "2023-06-01"},
                    }
                ]
            }
        ),
    )
    get_test = Mock()
    monkeypatch.setattr(client, "get_test", get_test)
    target = tmp_path / "export" / "20230601_TC7FC5XSW.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"data": {"type": "test", "id": "TC7FC5XSW", "attributes": {"state": "complete"}}}')

    export.export_account(
        client=client,
        output_directory=tmp_path / "export",
    )

    get_test.assert_not_called()


def test_export_account_skips_active_test_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = export.ThrivaClient.__new__(export.ThrivaClient)
    monkeypatch.setattr(
        client,
        "list_tests",
        Mock(
            return_value={
                "data": [
                    {
                        "type": "test",
                        "id": "TC7FC5XSW",
                        "attributes": {
                            "state": "active",
                            "test_date": "2023-06-01",
                        },
                    }
                ]
            }
        ),
    )
    get_test = Mock()
    monkeypatch.setattr(client, "get_test", get_test)
    target = tmp_path / "export" / "20230601_TC7FC5XSW.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"data": {"type": "test", "id": "TC7FC5XSW", "attributes": {"state": "active"}}}')

    export.export_account(
        client=client,
        output_directory=tmp_path / "export",
    )

    get_test.assert_not_called()
    assert not target.exists()
