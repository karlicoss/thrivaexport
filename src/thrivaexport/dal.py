from __future__ import annotations

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from hpikit.datetime import AwareDateTime, aware
from hpikit.json import Json, loads

type ResourceKey = tuple[str, str]


def _attributes(resource: Json) -> Json:
    value = resource.get("attributes", {})
    assert isinstance(value, dict), value
    return value


def _string_attribute(resource: Json, name: str) -> str | None:
    value = _attributes(resource).get(name)
    assert value is None or isinstance(value, str), value
    return value


def _resource_key(resource: Json) -> ResourceKey:
    type_ = resource["type"]
    id_ = resource["id"]
    assert isinstance(type_, str), type_
    assert isinstance(id_, str), id_
    return (type_, id_)


def _included_index(document: Json) -> dict[ResourceKey, Json]:
    included = document.get("included", [])
    assert isinstance(included, list), included
    result = {}
    for resource in included:
        assert isinstance(resource, dict), resource
        result[_resource_key(resource)] = resource
    return result


def _relationship_data(resource: Json, name: str) -> Any | None:
    relationships = resource.get("relationships", {})
    assert isinstance(relationships, dict), relationships
    relation = relationships.get(name)
    if relation is None:
        return None
    assert isinstance(relation, dict), relation
    return relation.get("data")


def _relation_keys(resource: Json, name: str) -> list[ResourceKey]:
    data = _relationship_data(resource, name)
    if data is None:
        return []
    if isinstance(data, list):
        keys = []
        for child in data:
            assert isinstance(child, dict), child
            keys.append(_resource_key(child))
        return keys
    assert isinstance(data, dict), data
    return [_resource_key(data)]


def _format_value(*, value: float | str | bool | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return f"{value:g}"
    return value


def _format_result(result: AnalyteResult) -> str:
    value = _format_value(value=result.value)
    if value == "":
        return ""
    unit = result.unit
    if unit is None:
        return value
    return f"{value} {unit}"


@dataclass(frozen=True)
class Snapshot:
    root: Path
    test_files: list[Path]

    @classmethod
    def load(cls, source: Path | str) -> Snapshot:
        root = Path(source)
        if root.is_file():
            root = root.parent
        root = root.resolve()

        test_files = sorted(root.glob("*.json"))
        assert len(test_files) > 0, root
        for path in test_files:
            test = ThrivaTest.load(path)
            assert test.raw["type"] == "test", (path, test.raw)
            assert test.state == "complete", (path, test.state)

        return cls(
            root=root,
            test_files=test_files,
        )


@dataclass(frozen=True)
class AnalyteResult:
    raw: Json
    analyte: Json | None

    @property
    def id(self) -> str:
        value = self.raw["id"]
        assert isinstance(value, str), value
        return value

    @property
    def code(self) -> str:
        attributes = _attributes(self.raw)
        value = attributes["analyte_id"]
        assert isinstance(value, str), value
        return value

    @property
    def name(self) -> str:
        if self.analyte is None:
            return self.code
        value = _attributes(self.analyte).get("name")
        assert isinstance(value, str), value
        return value

    @property
    def value(self) -> float | str | bool | None:
        value = _attributes(self.raw).get("value")
        assert value is None or isinstance(value, int | float | str | bool), value
        return value

    @property
    def unit(self) -> str | None:
        return _string_attribute(self.raw, "unit")

    @property
    def label(self) -> str | None:
        return _string_attribute(self.raw, "label")

    @property
    def severity(self) -> str | None:
        return _string_attribute(self.raw, "severity")

    @property
    def processed_at(self) -> AwareDateTime | None:
        value = _string_attribute(self.raw, "processed_at")
        if value is None:
            return None
        return aware(datetime.fromisoformat(value))


@dataclass(frozen=True)
class ThrivaTest:
    path: Path
    raw: Json
    included: dict[ResourceKey, Json]

    @classmethod
    def load(cls, path: Path) -> ThrivaTest:
        document = loads(path.read_bytes())
        assert isinstance(document, dict), document
        data = document["data"]
        assert isinstance(data, dict), data
        return cls(
            path=path,
            raw=data,
            included=_included_index(document),
        )

    @property
    def id(self) -> str:
        value = self.raw["id"]
        assert isinstance(value, str), value
        return value

    @property
    def state(self) -> str:
        value = _attributes(self.raw)["state"]
        assert isinstance(value, str), value
        return value

    @property
    def date(self) -> str | None:
        for key in ["test_date", "scheduled_date"]:
            value = _string_attribute(self.raw, key)
            if value is not None:
                return value
        return None

    @property
    def completed_at(self) -> AwareDateTime | None:
        value = _string_attribute(self.raw, "completed_at")
        if value is None:
            return None
        return aware(datetime.fromisoformat(value))

    @property
    def package_name(self) -> str | None:
        return _string_attribute(self.raw, "package_name")

    def related(self, name: str) -> list[Json]:
        resources = []
        for key in _relation_keys(self.raw, name):
            resource = self.included.get(key)
            if resource is not None:
                resources.append(resource)
        return resources

    def analyte_results(self) -> Iterator[AnalyteResult]:
        for resource in self.included.values():
            if resource["type"] != "analyte_result":
                continue
            analyte = None
            analyte_keys = _relation_keys(resource, "analyte")
            if len(analyte_keys) > 0:
                analyte = self.included.get(analyte_keys[0])
            yield AnalyteResult(raw=resource, analyte=analyte)


class DAL:
    """Offline access to one Thriva export snapshot."""

    def __init__(self, source: Path | str) -> None:
        self.snapshot = Snapshot.load(source)

    def tests(self) -> Iterator[ThrivaTest]:
        tests = [ThrivaTest.load(path) for path in self.snapshot.test_files]
        yield from sorted(tests, key=lambda test: (test.date or "", test.id))


def _summary_table(tests: list[ThrivaTest]) -> tuple[list[str], list[list[str]]]:
    codes = sorted({result.code for test in tests for result in test.analyte_results()})
    headers = ["date", "state", "package", *codes]
    rows = []
    for test in tests:
        results = {result.code: _format_result(result) for result in test.analyte_results()}
        rows.append(
            [
                test.date or "",
                test.state,
                test.package_name or "",
                *[results.get(code, "") for code in codes],
            ]
        )
    return headers, rows


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Thriva exports offline through the DAL.")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Thriva export directory or a file within it",
    )
    return parser


def main() -> None:
    from tabulate import tabulate

    args = _make_parser().parse_args()
    dal = DAL(args.source)

    tests = list(dal.tests())
    print(f"Source: {dal.snapshot.root}")
    print(f"Tests: {len(tests)}")
    if len(tests) > 0:
        print(f"Range: {tests[0].date} to {tests[-1].date}")
        print(f"Analyte results: {sum(1 for test in tests for _ in test.analyte_results())}")
        headers, rows = _summary_table(tests)
        print()
        print(tabulate(rows, headers=headers, tablefmt="github"))


if __name__ == "__main__":
    main()
