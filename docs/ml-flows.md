# Lightweight workbench flows

> Small synchronous helpers in [`aqp.ml.flows`](../aqp/ml/flows.py) that
> let users iterate on a dataset without spinning up a full
> `Experiment`. Surfaced at `POST /ml/flows/{flow}/preview`,
> `POST /ml/flows/{flow}/preview-task` (Celery), and `GET /ml/flows`
> (catalog).

## Catalog

| Flow | Purpose | Backend |
| --- | --- | --- |
| `linear` | Ridge / Lasso / ElasticNet / BayesianRidge with IC + RMSE / MAE | sklearn |
| `decomposition` | STL trend / seasonal / residual | statsmodels |
| `forecast` | Prophet / sktime-naive / ARIMA / ETS / Theta / AutoARIMA | mixed |
| `regression_diagnostics` | OLS coef table, R^2, F-stat, Durbin-Watson | statsmodels |
| `unit_root` | ADF / KPSS unit-root tests | statsmodels |
| `acf_pacf` | Auto- and partial-autocorrelation series | statsmodels |
| `granger_causality` | Granger causality between two columns | statsmodels |
| `cointegration` | Engle-Granger pair cointegration | statsmodels |
| `garch` | GARCH(p, q) volatility model + horizon | arch |
| `change_point` | PELT / RBF kernel change points | ruptures |
| `clustering` | KMeans / DBSCAN / HDBSCAN on the feature matrix | sklearn / hdbscan |
| `pca_summary` | PCA variance + factor loadings | sklearn |

## REST surface

```bash
# List every flow + its parameter schema
curl http://localhost:8000/ml/flows | jq

# Sync run a flow
curl -XPOST http://localhost:8000/ml/flows/linear/preview \
  -d '{"dataset_cfg": {...}, "estimator": "ridge", "alpha": 1.0}' \
  -H 'content-type: application/json'

# Background run via Celery (returns TaskAccepted)
curl -XPOST http://localhost:8000/ml/flows/garch/preview-task \
  -d '{"dataset_cfg": {...}, "column": "close", "p": 1, "q": 1, "horizon": 10}' \
  -H 'content-type: application/json'
```

## Webui workbench drawer

The ML Experiment Builder
([`/ml/builder`](../webui/app/(shell)/ml/builder/page.tsx)) ships an
"Interactive Workbench" drawer on its toolbar. Pick a flow, fill in
the per-flow form (auto-generated from `GET /ml/flows`), and submit —
the result table renders inline so you never leave the canvas.

## Tutorials

- [01_quick_ridge_workbench.yaml](../configs/ml/tutorials/01_quick_ridge_workbench.yaml)
- [02_stl_decompose_workbench.yaml](../configs/ml/tutorials/02_stl_decompose_workbench.yaml)
- [03_arima_garch_diagnostics.yaml](../configs/ml/tutorials/03_arima_garch_diagnostics.yaml)

## Adding a new flow

1. Implement `run_<flow>_flow(...)` in
   [`aqp/ml/flows.py`](../aqp/ml/flows.py) returning a `FlowResult`.
2. Add a dispatch branch in `run_flow(flow, payload)`.
3. Add an entry in `list_flows()` so the webui form reflects the new
   parameters automatically.
4. (Optional) Wrap as a notebook helper in
   [`aqp/ml/adhoc/`](../aqp/ml/adhoc/__init__.py).
