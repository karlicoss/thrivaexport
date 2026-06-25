# Thriva exporter

This repository follows the export/DAL split described in
[Building data liberation infrastructure](https://beepb00p.xyz/exports.html):

- the **export layer** communicates with Thriva and preserves raw JSON:API data;
- the **data access layer (DAL)** works offline and interprets exported data.

The implementation lives under `src/thrivaexport`:

```text
src/thrivaexport/
  common.py   shared archive primitives
  export.py   API access and raw export
  dal.py      offline access and typed Thriva bindings
```

## Exporting

Create `secrets.json`:

```json
{
  "email": "name@example.com",
  "password": "your Thriva password"
}
```

Run the exporter:

```console
uv run --extra export -m thrivaexport.export \
  --secrets secrets.json \
  --output exports/thriva
```

For incremental updates, reuse the same output directory. The exporter checks
Thriva's test list every run and downloads detailed records only for complete
tests. Active and scheduled tests are ignored until Thriva marks them complete.

Useful options:

```console
uv run --extra export -m thrivaexport.export \
  --secrets secrets.json \
  --output exports/thriva \
  --refresh-existing
```

The exporter writes raw JSON only. Credentials stay in `secrets.json`, which is
ignored by git.

## Raw archive

The exporter writes:

```text
thriva-export/
  <date>_<test-id>.json
```

Each test file is the detailed `/tests/<id>` JSON:API response with related
resources included. Detailed files are written for complete tests only.

## Offline DAL

Inspect an archive without `requests` or network access:

```console
uv run --extra dal -m thrivaexport.dal --source exports/thriva
```

The command prints one row per test, with status and one column per observed
analyte result.

Programmatic access from the repository root:

```python
from thrivaexport.dal import DAL

dal = DAL("exports/thriva")

for test in dal.tests():
    print(test.date, test.id, test.state)

    for result in test.analyte_results():
        print(result.name, result.value, result.unit, result.label)
```

## Verification

```console
uv run --extra export -m thrivaexport.export --help
uv run --extra dal -m thrivaexport.dal --source exports/thriva
uv run pytest
uv run ruff check .
uv run mypy src
```

The API is undocumented and may change. See [docs/research.md](docs/research.md)
for research and protocol details, and [docs/data_notes.md](docs/data_notes.md)
for observed data quirks.
