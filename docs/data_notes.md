# Data Notes

The preserved `legacy/res.json` sample is a detailed JSON:API response for one
completed test.

Observed top-level shape:

| Field      | Notes                                      |
|------------|--------------------------------------------|
| `data`     | Primary `test` resource                    |
| `included` | Related resources requested via `include=` |

Observed included resource types:

| Type                          | Notes                                      |
|-------------------------------|--------------------------------------------|
| `analyte`                     | Biomarker metadata                         |
| `analyte_result`              | Biomarker value, ranges, unit, label       |
| `doctor`                      | Report doctor metadata                     |
| `forecast`                    | Forecast/cadence metadata                  |
| `intervention`                | Recommendations                            |
| `intervention_analyte`        | Link between intervention and analyte      |
| `panel`                       | Ordered panel and profile configuration    |
| `profile`                     | Profile metadata and linked analytes       |
| `report`                      | Summary/user review fields                 |
| `report_analyte_comment`      | Text comment for a result                  |
| `shop_product`                | Products linked from interventions         |
| `test_cadence`                | Cadence metadata for analytes              |
| `test_failure_classification` | Failure/redeemable status metadata         |
| `test_result`                 | Result metadata                            |
| `test_result_attachment`      | Time-limited attachment URL                |

Attachment URLs are signed and expire. The exporter currently preserves them as
raw metadata and does not download attachments.
