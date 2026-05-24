# Analysis Lab — interactive analysis builder

> Backend: [aqp_docs/analysis-framework.md](analysis-framework.md) · Flow reference: [aqp_docs/analysis-flows.md](analysis-flows.md).

Lives at `/analysis/lab` in the AQP webui (Vite frontend). Hybrid
surface: dataset-centric tabbed drill-down (primary path) plus an
XYFlow Composer (secondary path) for multi-step pipelines.

## Layout

| Tab | Purpose | Driving flows |
| --- | --- | --- |
| **Profiling** | Column profile + null audit + topk + dtypes | `profiling.*` |
| **Distribution** | Descriptive stats / histogram / ECDF / Q-Q + Shapiro-Wilk / Jarque-Bera / K-S | `distribution.*` |
| **Outliers** | Z-score / IQR / Isolation Forest / DBSCAN / LOF / ECOD / pulse-vs-step | `outlier.*` |
| **Time Series** | ADF / KPSS / ACF-PACF / STL / GARCH / change-point / Granger / cointegration / FFT / wavelets / Hurst / Theil-Sen | `time_series.*` |
| **Regression** | OLS diagnostics / White / Breusch-Pagan / VIF | `regression.*` |
| **Imputation** | ffill/bfill / linear / spline / KNN / MICE | `imputation.*` |
| **Derivatives** | BSM + Greeks surface + IV / Monte-Carlo European / barrier / Asian / SABR smile / Bachelier | `derivatives.*` |
| **Portfolio** | Efficient frontier / Ledoit-Wolf / Fama-French 5 rolling / risk parity | `portfolio.*` |
| **Factors** | Alphalens-style IC + quantile spread + turnover | `factors.evaluate` |
| **Composer** | XYFlow canvas — drag analysis nodes, save spec, run via runtime | every namespace |

Each tab loads the relevant flow schemas via `GET /analysis/flows`,
auto-generates the form, and submits to `POST /analysis/flows/{flow}/preview`.
Charts render inline (Plotly figure-dict in the response).

The "Save as spec" button on any tab promotes the current state into
an `AnalysisSpec` and routes to the Composer for multi-step editing
without losing context.

## Routes

| Path | Component |
| --- | --- |
| `/analysis/lab` | Tabbed primary surface |
| `/analysis/lab/composer` | XYFlow Composer (XYFlow canvas + ANALYSIS_PALETTE) |
| `/analysis/runs` | Run ledger (paged) |
| `/analysis/runs/[id]` | Run detail (steps + chart previews) |

The Composer reuses the existing
[`WorkflowEditor`](../aqp_client/src/components/flow/WorkflowEditor.tsx) with
`domain="analysis"`. The serializer turns the canvas graph into an
`AnalysisSpec` payload, posts it to `POST /analysis/specs`, then to
`POST /analysis/specs/{slug}/run`.

## API surface used

- `GET  /analysis/flows` — flow catalog with JSON-schema params.
- `POST /analysis/flows/{flow}/preview` — sync preview.
- `POST /analysis/flows/{flow}/preview-task` — Celery preview.
- `POST /analysis/specs` — persist (hash-idempotent).
- `POST /analysis/specs/{slug}/run` — queue `AnalysisRuntime.run` task.
- `GET  /analysis/runs` / `GET /analysis/runs/{id}` — ledger.
- `GET  /analysis/runs/{id}/results/{step}` — DuckDB preview of the
  gold-tier output for one step.
- `GET  /analysis/datasets/columns?identifier=ns.name` — column list
  used by the lab's column-autocomplete inputs.

## Cross-links

The lab does not reinvent existing surfaces — it deep-links into them
when the user wants a richer experience:

- Derivatives tab → [`/options/lab`](../aqp_client/src/routes/options/lab/page.tsx)
  for instrument-level workflows.
- Portfolio tab → [`/optimizer`](../aqp_client/src/routes/optimizer/page.tsx)
  for multi-strategy parameter sweeps.
- Factors tab wraps the existing
  [`FactorWorkbench`](../aqp_client/src/components/factors/FactorWorkbench.tsx).
- Visualisations of Iceberg outputs deep-link into
  [`/visualizations`](../aqp_client/src/routes/visualizations/page.tsx).
