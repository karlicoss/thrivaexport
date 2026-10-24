from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, cast

import requests
from hpikit.json import Json
from kloggy import get_logger

logger = get_logger(__name__)

_API_URL = "https://api.thriva.co/v1"
_AUTH_URL = "https://api.thriva.co/auth/token"
_APP_URL = "https://app.thriva.co"

_RETRYABLE_STATUS_CODES = {
    429,  # Too Many Requests: rate limiting; Retry-After is handled below.
    500,  # Internal Server Error: intermittent Thriva/server failure.
    502,  # Bad Gateway: proxy could not reach an upstream server.
    503,  # Service Unavailable: temporary overload or maintenance.
    504,  # Gateway Timeout: upstream server did not respond in time.
}


def _load_secrets(path: Path) -> Json:
    secrets = json.loads(path.read_text())
    assert isinstance(secrets, dict), secrets
    return secrets


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def _safe_file_name(name: str) -> str:
    assert name not in {"", ".", ".."}, name
    assert "/" not in name, name
    assert "\\" not in name, name
    return name


def _test_sort_key(resource: Json) -> str:
    attributes = resource.get("attributes", {})
    assert isinstance(attributes, dict), attributes
    for key in ["test_date", "scheduled_date", "completed_at", "created_at"]:
        value = attributes.get(key)
        if isinstance(value, str):
            return value[:10].replace("-", "")
    return "unknown"


def _test_file_name(resource: Json) -> str:
    type_ = resource["type"]
    id_ = resource["id"]
    assert type_ == "test", resource
    assert isinstance(id_, str), id_
    return f"{_test_sort_key(resource)}_{_safe_file_name(id_)}.json"


def _relationship_names(resource: Json) -> list[str]:
    """
    Return names of linked resources advertised by a JSON:API object.

    Thriva uses the JSON:API "relationships" field to point at related objects
      such as panels, profiles, analytes, reports, and result comments.
    These names become candidates for the `include=` query parameter.
    """
    relationships = resource.get("relationships", {})
    assert isinstance(relationships, dict), relationships
    return sorted(relationships)


def _retry_delay(response: requests.Response, attempt: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None and retry_after.isdigit():
        return int(retry_after)
    return 1 << attempt


class ThrivaClient:
    def __init__(self) -> None:
        self.http = requests.Session()
        self.http.headers.update(
            {
                "Accept": "application/vnd.api+json",
                "Origin": _APP_URL,
                "Referer": f"{_APP_URL}/",
                "User-Agent": "thrivaexport/1",
            }
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        attempts: int = 4,
        **kwargs: Any,
    ) -> requests.Response:
        for attempt in range(attempts):
            try:
                response = self.http.request(method, url, **kwargs)
            except requests.ConnectionError, requests.Timeout:
                if attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)
                continue

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                return response
            if attempt == attempts - 1:
                return response
            time.sleep(_retry_delay(response, attempt))
        raise AssertionError

    def authenticate(
        self,
        *,
        email: str,
        password: str,
    ) -> Json:
        response = self.request(
            "POST",
            _AUTH_URL,
            json={
                "grant_type": "password",
                "type": "user",
                "username": email,
                "password": password,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        value = response.json()
        assert isinstance(value, dict), value

        return self.get_json(
            "/self",
            params={"include": "user_preference"},
        )

    def get_json(
        self,
        endpoint_or_url: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Json:
        url = endpoint_or_url if endpoint_or_url.startswith("http") else _API_URL + endpoint_or_url
        response = self.request(
            "GET",
            url,
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        value = response.json()
        assert isinstance(value, dict), value
        return value

    def list_tests(
        self,
        *,
        limit: int = 20,
    ) -> Json:
        tests: list[Json] = []
        offset = 0
        next_url: str | None = None
        using_link_pagination = False

        while True:
            params: dict[str, str | int] | None
            if next_url is None:
                params = {
                    "filter[state]": "complete",
                    "limit": limit,
                    "offset": offset,
                }
                document = self.get_json("/tests", params=params)
            else:
                document = self.get_json(next_url)

            data = document["data"]
            assert isinstance(data, list), data
            for resource in data:
                assert isinstance(resource, dict), resource
                tests.append(resource)

            links = document.get("links", {})
            assert isinstance(links, dict), links
            raw_next = links.get("next")
            assert raw_next is None or isinstance(raw_next, str), raw_next
            if raw_next is not None:
                next_url = raw_next
                using_link_pagination = True
                continue
            if using_link_pagination:
                break

            meta = document.get("meta", {})
            assert isinstance(meta, dict), meta
            pagination = meta.get("pagination")
            if pagination is not None:
                assert isinstance(pagination, dict), pagination
                raw_limit = pagination["limit"]
                raw_offset = pagination["offset"]
                raw_total_count = pagination["total_count"]
                assert isinstance(raw_limit, int), raw_limit
                assert isinstance(raw_offset, int), raw_offset
                assert isinstance(raw_total_count, int), raw_total_count
                offset = raw_offset + raw_limit
                if offset >= raw_total_count:
                    break
                continue

            if len(data) < limit:
                break
            offset += len(data)
            next_url = None

        return {"data": tests}

    def discover_test_includes(
        self,
        test_id: str,
        *,
        max_depth: int = 4,
    ) -> tuple[Json, list[str]]:
        """
        Discover accepted JSON:API include paths for one test resource.

        Thriva rejects some advertised relationships as include paths.
        This probes paths one at a time and ignores only invalid-parameter
          responses.
        Depth 4 covers the deepest useful path observed so far:
        test -> panel -> profiles -> analytes.
        A higher limit would mostly add requests for relationships on leaf
          metadata resources.
        """
        base = self.get_json(f"/tests/{test_id}")
        data = base["data"]
        assert isinstance(data, dict), data

        accepted = []
        seen = set()
        queue = _relationship_names(data)
        for _depth in range(max_depth):
            next_queue = []
            for path in queue:
                if path in seen:
                    continue
                seen.add(path)
                try:
                    document = self.get_json(
                        f"/tests/{test_id}",
                        params={"include": path},
                    )
                except requests.HTTPError as e:
                    response = e.response
                    if response is not None and response.status_code == 400:
                        continue
                    raise

                accepted.append(path)
                included = document.get("included", [])
                assert isinstance(included, list), included
                for resource in included:
                    assert isinstance(resource, dict), resource
                    for relationship in _relationship_names(resource):
                        next_queue.append(f"{path}.{relationship}")

            queue = sorted(set(next_queue))
            if len(queue) == 0:
                break

        return base, accepted

    def get_test(self, test_id: str) -> Json:
        base, include_paths = self.discover_test_includes(test_id)
        if len(include_paths) == 0:
            return base
        return self.get_json(
            f"/tests/{test_id}",
            params={"include": ",".join(include_paths)},
        )


def _existing_detail_path(*, output_directory: Path, test: Json) -> Path | None:
    test_id = test["id"]
    assert isinstance(test_id, str), test_id
    matches = sorted(output_directory.glob(f"*_{test_id}.json"))
    if len(matches) == 0:
        return None
    assert len(matches) == 1, matches
    return matches[0]


def export_account(
    *,
    client: ThrivaClient,
    output_directory: Path,
    refresh_existing: bool = False,
) -> None:
    index = client.list_tests()
    tests = index["data"]
    assert isinstance(tests, list), tests

    # We intentionally list only completed tests.
    # Active/scheduled tests are not persisted because their detail file would
    #   later need to change in place when blood results arrive.
    logger.info(f"Found {len(tests)} tests")
    for index_, summary_raw in enumerate(tests, start=1):
        assert isinstance(summary_raw, dict), summary_raw
        summary = cast(Json, summary_raw)
        test_id = summary["id"]
        assert isinstance(test_id, str), test_id
        path = _existing_detail_path(output_directory=output_directory, test=summary)
        attributes = summary.get("attributes", {})
        assert isinstance(attributes, dict), attributes
        test_date = attributes.get("test_date", "unknown-date")
        state = attributes.get("state", "unknown-state")

        if state != "complete":
            if path is not None:
                path.unlink()
            logger.info(f"[{index_}/{len(tests)}] {test_date} {state} (skip)")
            continue

        if path is None:
            path = output_directory / _test_file_name(summary)

        should_fetch = refresh_existing or not path.exists()
        status = "refresh" if should_fetch else "existing"
        logger.info(f"[{index_}/{len(tests)}] {test_date} {state} ({status})")
        if should_fetch:
            detail = client.get_test(test_id)
            _write_json(path, detail)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export raw Thriva tests and results.")
    parser.add_argument(
        "--secrets",
        type=Path,
        required=True,
        help="JSON file containing email and password",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Archive directory",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Re-fetch detailed records even when an existing complete record is present",
    )
    return parser


def main() -> None:
    args = _make_parser().parse_args()

    secrets = _load_secrets(args.secrets)
    email = secrets["email"]
    password = secrets["password"]
    assert isinstance(email, str), type(email)
    assert isinstance(password, str), type(password)

    client = ThrivaClient()
    client.authenticate(
        email=email,
        password=password,
    )

    export_account(
        client=client,
        output_directory=args.output,
        refresh_existing=args.refresh_existing,
    )
    logger.info(f"Archive written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
