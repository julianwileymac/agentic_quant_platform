# Interactive ML testing workbench

> The `/ml/test` page lets users validate deployed models with single
> rows, batch slices, A/B comparisons, perturbation sweeps, CSV
> uploads, and live streaming — all wired through the same
> [`DeployedModelAlpha`](../aqp/strategies/ml_alphas.py) runtime that
> production strategies use.

## Tabs

| Tab | Endpoint(s) | Behaviour |
| --- | --- | --- |
| Single Predict | `POST /ml/test/single` (sync) | Score one row, render score + sign |
| Batch | `POST /ml/test/batch` (Celery) + `POST /ml/test/upload-csv` | Iceberg slice or uploaded CSV scoring |
| A/B Compare | `POST /ml/test/compare` (Celery) | Side-by-side signals + agreement rate |
| Scenario / What-if | `POST /ml/test/scenario` (sync) | Per-feature ±N% perturbation table + heatmap |
| Historical | `POST /ml/evaluate` (Celery) | Existing offline eval flow |
| Live | `POST /ml/live-test/start` + WS bridge | Stream bars / signals from a venue |
| Models | n/a | Tabular `ModelVersion` browser |

## Backend

[`aqp/tasks/ml_test_tasks.py`](../aqp/tasks/ml_test_tasks.py) hosts the
Celery tasks (queue `ml`):

- `predict_single` — single-row inference
- `predict_batch` — Iceberg slice scoring
- `compare_models` — A/B between two `model_version_id`s
- `scenario_perturbation` — sensitivity table

Each task routes through [`DeployedModelAlpha._predict`](../aqp/strategies/ml_alphas.py)
so dataset-driven AND legacy indicator-zoo paths both work.

## Sample REST calls

```bash
# Single prediction (sync)
curl -XPOST http://localhost:8000/ml/test/single \
  -d '{"deployment_id": "...", "feature_row": {"f1": 0.1, "f2": -0.4}, "sync": true}' \
  -H 'content-type: application/json'

# Scenario sweep
curl -XPOST http://localhost:8000/ml/test/scenario \
  -d '{"deployment_id": "...", "feature_row": {"f1": 0.1, "f2": -0.4}, "perturbations": [-0.1, 0, 0.1]}' \
  -H 'content-type: application/json'

# CSV upload (multipart)
curl -XPOST 'http://localhost:8000/ml/test/upload-csv?deployment_id=...' \
  -F 'file=@features.csv'
```

The CSV upload path is capped via
``settings.ml_workbench_max_csv_mb`` (default 20 MB).

## Visualisations

The webui renders results with
[`recharts`](https://recharts.org/) (already a dependency):

- Single Predict — Descriptions card with score + bias tag.
- Scenario — `BarChart` of deltas + sortable Ant Design table.
- Live — line chart overlay of bar close + signal strength + recent
  events list.

## Where this gets called from

- Standalone: `/ml/test`.
- ML Builder: a `Test*` node on the canvas serializes to the
  matching `/ml/test/*` endpoint.
- AlphaBacktestExperiment: when `train_first=true` it stamps the new
  deployment id on `MLAlphaBacktestRun`, so the next visit to
  `/ml/test` can score against it directly.
