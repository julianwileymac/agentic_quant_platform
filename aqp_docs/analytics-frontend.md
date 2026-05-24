# Interactive analytics in the Vite frontend (Phase 4)

> Companion to [aqp_docs/portfolio-options-mm.md](portfolio-options-mm.md).
> This doc covers the post-Phase-7 cutover analytics surfaces that
> moved the QuantStats + ML test visualisations out of legacy Solara
> / Dash and into the Vite app.

## TL;DR — no Streamlit

The original refactor report recommended Streamlit. The AQP frontend
cutover to Vite + React 19 + Tailwind 4 + shadcn/ui is **complete**
(see [aqp_client/CUTOVER.md](../aqp_client/CUTOVER.md)). All new
analytics ship as Vite routes + components; no Streamlit dependency
is introduced.

## Backend

Three thin FastAPI routers:

- [aqp/api/routes/analytics_portfolio.py](../aqp/api/routes/analytics_portfolio.py)
  - `POST /analytics/portfolio/metrics` — fast synchronous Sharpe /
    Sortino / MaxDD / CAGR / Calmar / Tail ratio (QuantStats).
  - `POST /analytics/portfolio/rolling` — rolling Sharpe / rolling
    volatility / underwater.
  - `POST /analytics/portfolio/tearsheet` — enqueues the heavy
    `quantstats.reports.html` render through Celery.
  - `POST /analytics/portfolio/tearsheet-sync` — opt-in inline
    fallback for dev environments without a Celery worker.
- [aqp/api/routes/analytics_ml.py](../aqp/api/routes/analytics_ml.py)
  - `POST /analytics/ml/distribution-overlay`
  - `POST /analytics/ml/drift-heatmap`
  - `POST /analytics/ml/perturbation-sweep`
- [aqp/tasks/analytics_tasks.py](../aqp/tasks/analytics_tasks.py)
  - `render_portfolio_tearsheet` Celery task. Uses the `Agg`
    matplotlib backend — never `fig.show()`. Progress flows through
    the canonical `emit / emit_done / emit_error` (AGENTS rule 4).

## Frontend

- `aqp_client/src/lib/api/analytics.ts` — typed client.
- `aqp_client/src/components/analytics/`
  - `TearSheetGrid.tsx` — metrics dashboard (Sharpe, Sortino, CAGR…)
  - `RollingPanel.tsx` — rolling Sharpe / vol with `recharts`
  - `UnderwaterPanel.tsx` — drawdown area (`recharts`)
  - `DrawdownTable.tsx` — top-N drawdowns extracted from the
    underwater series
  - `DistributionOverlay.tsx` — actual vs predicted histograms
- `aqp_client/src/routes/analytics/portfolio/[runId]/page.tsx`
- `aqp_client/src/routes/analytics/ml/[runId]/page.tsx`

Both routes read the underlying numeric series from
`sessionStorage[aqp.analytics.*]`. The originating run page (backtest
detail, paper detail, ML test detail) is the natural stage to write
that key before navigating; the analytics route stays a pure consumer
so it can be embedded from anywhere.

## pandas-ta-classic wiring

`from_pandas_ta` in
[aqp/data/indicators_zoo.py](../aqp/data/indicators_zoo.py) already
gates the import behind a lazy `try/except ImportError` chain
(`pandas_ta` → `pandas_ta_classic`). The package ships in the
`[ml]` optional extra so the core install footprint stays small.
