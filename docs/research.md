# Research

## Export design

The implementation follows the split described in
<https://beepb00p.xyz/exports.html>:

| Layer        | Responsibility                                      |
|--------------|-----------------------------------------------------|
| Export       | Fetch raw data from Thriva and persist it unchanged |
| DAL          | Read local files and expose small typed helpers     |
| Consumers    | Analyse or display data using the DAL               |

The current exporter is incremental. It checks Thriva's test list on every run
and fetches detailed records only for complete tests. Active and scheduled tests
are ignored until Thriva marks them complete.

## Existing public work

I searched for reusable public attempts before implementing this:

| Query                         | Result                                          |
|-------------------------------|-------------------------------------------------|
| `site:github.com Thriva API`  | No reusable exporter or client surfaced         |
| `site:github.com Thriva data` | No relevant data export project surfaced        |
| `api.thriva.co`               | No public project with a complete client found  |
| `thriva export python`        | No relevant Python exporter surfaced            |

GitHub's code search UI was not accessible through the browser tool in this
environment, so this is based on targeted web search rather than authenticated
GitHub code search.

## Observed Thriva API

The old local attempt in `legacy/` showed the useful endpoint:

```text
https://api.thriva.co/v1/tests/<test-id>
```

The old successful detailed request used JSON:API and this include set:

```text
panel.profiles.analytes,
result,
result.analyte_results,
result.attachments,
report.analyte_comments,
report.doctor,
interventions,
interventions.intervention_analytes,
interventions.products,
test_failure_classification,
test_cadences,
forecasts,
request.organization
```

The exporter does not hardcode this list. It starts from the test resource's
relationships and probes accepted JSON:API include paths recursively, then uses
the discovered paths for the detailed export.

The old scripts contained stale cookies/JWT values, so they are kept under the
gitignored `legacy/` directory as local reference material only.

## Authentication

The current Thriva frontend posts to:

```text
https://api.thriva.co/auth/token
```

with this JSON body:

```json
{
  "grant_type": "password",
  "type": "user",
  "username": "<email>",
  "password": "<password>"
}
```

A live smoke test on 2026-06-25 returned HTTP 201, established a session, and
then `GET https://api.thriva.co/v1/self` returned HTTP 200.

The exporter supports email/password secrets:

```json
{"email": "name@example.com", "password": "your Thriva password"}
```
