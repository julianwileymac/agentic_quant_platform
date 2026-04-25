# Agentic Quant Platform (AQP)

A **local-first, agentic quantitative research and trading platform** that fuses Agent-Ops and RL-Ops into a single autonomous laboratory. Every LLM call, every backtest, every reinforcement-learning rollout, and every piece of metadata stays on your hardware — no proprietary alpha traverses external APIs.

AQP distills architectural patterns from the best-of-breed open-source quant ecosystem:

| Inspiration | Pattern adopted |
|---|---|
| [Microsoft Qlib](https://github.com/microsoft/qlib) | `class`/`module_path`/`kwargs` factory; symbolic feature expressions; MLflow-backed recorder |
| [AI4Finance FinRL](https://github.com/AI4Finance-Foundation/FinRL) | `gym.Env` policy contract; pluggable `DataProcessor`; thin SB3 adapters |
| [QuantConnect Lean](https://github.com/QuantConnect/Lean) | 5-stage framework pipeline (Universe → Alpha → Portfolio → Risk → Execution); **`IBrokerage` + `IDataQueueHandler` parity across backtest / paper / live** |
| [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) | "Connect once, consume everywhere" adapter surface for vendors |
| [vnpy](https://github.com/vnpy/vnpy) | `BaseGateway` + `EventEngine`; immutable `vt_symbol` IDs; plugin registration |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Dual-tier LLMs; per-role BM25 memory; bounded debate graphs |

## Architecture

```
                     ┌──────────────────────┐
                     │  Next.js webui :3000 │
                     │  (React + Ant + Flow │
                     │   + AG Grid + WS)    │
                     └──────────┬───────────┘
                                │ REST / WebSocket
                     ┌──────────▼───────────┐
                     │   FastAPI Gateway    │
                     └──────────┬───────────┘
                                │
            ┌───────────────────┴───────────────────┐
            │           Redis  (broker + pubsub)    │
            └─────┬──────────────────────────┬──────┘
                  │                          │
       ┌──────────▼───────────┐   ┌──────────▼────────────┐
       │  Celery Workers      │   │  Celery Workers (GPU) │
       │  - Backtesting       │   │  - RL Training        │
       │  - Agent Crews       │   │  - Large LLM inf.     │
       │  - Ingestion         │   │                       │
       └──────────┬───────────┘   └──────────┬────────────┘
                  │                          │
    ┌─────────────┴──────────────┬───────────┴───────────────┐
    │                            │                           │
┌───▼─────┐  ┌──────────┐  ┌─────▼─────┐  ┌─────────┐  ┌─────▼──────┐
│ DuckDB  │  │ ChromaDB │  │ PostgreSQL│  │ MLflow  │  │   Ollama   │
│ Parquet │  │ Vectors  │  │  Ledger   │  │Tracking │  │ (Nemotron) │
└─────────┘  └──────────┘  └───────────┘  └─────────┘  └────────────┘
```

## What's new in 0.7 — Next.js webui + visual workflow editors

The frontend has been rewritten in **React 19 / Next.js 15 / TypeScript**
under `webui/` (port `:3000`). Highlights:

- **Strangler migration** — the legacy Solara UI on `:8765` is now in a
  `legacy` Docker Compose profile; the Next.js app is the default.
- **Ant Design 5** shell (Plane-inspired sidebar + topbar + Cmd-K palette).
- **AG Grid Community** wrappers across Strategies, Backtests, Orders,
  Fills, Positions, Ledger, ML Models, Sources.
- **React Flow v12** (`@xyflow/react`) editors for three workflow domains:
  Agent Crew (Flowise-style), Data Pipeline, Strategy Composer — each
  serializes to JSON / YAML and POSTs to the existing FastAPI surface.
- **Type-safe REST client** — `openapi-typescript` + `openapi-fetch`
  regenerated from `python -m scripts.export_openapi` (`make webui-gen-api`).
- **WebSocket hooks** — `useChatStream` and `useLiveStream` wrap the
  existing `/chat/stream/{task_id}` and `/live/stream/{channel_id}` paths
  with reconnect, backoff, typed events.
- **Chat upgrades** — threaded chat page, floating Cmd-K assistant on every
  page, page-context (`vt_symbol`, `backtest_id`, …) injected automatically
  via the new `ChatContext` field on `POST /chat`.
- **CORS** is now env-driven via `AQP_WEBUI_CORS_ORIGINS` (empty = legacy
  `*` behaviour for back-compat).

See [`docs/webui.md`](docs/webui.md) for the full developer guide.

## What's new in 0.6 — Data plane expansion

The data layer now spans far beyond OHLCV bars:

- **Source registry** — every data source (yfinance, Polygon, Alpha
  Vantage, IBKR, local files, Alpaca, CCXT, **FRED**, **SEC EDGAR**,
  **GDelt**) has a row in the new `data_sources` table with its kind,
  auth type, capabilities, rate limits and credential env-var name.
  Manage it from REST (`/sources`), Solara (`/sources` page), or CLI
  (`aqp data sources list|probe|toggle`).
- **Alpha Vantage primary policy** — market bars and fundamentals now
  support provider policy knobs:
  `AQP_MARKET_BARS_PROVIDER=auto|alpha_vantage|yfinance`,
  `AQP_FUNDAMENTALS_PROVIDER=auto|alpha_vantage|yfinance`, and
  `AQP_ALPHA_VANTAGE_API_KEY`. In `auto`, Alpha Vantage is primary when
  configured with automatic yfinance fallback. The richer in-repo Alpha
  Vantage client also powers `/alpha-vantage/*` REST endpoints, provider
  catalog fetchers, Celery-backed bulk loads, and the Next.js
  `/alpha-vantage` admin/data UI. See [`docs/alpha-vantage.md`](docs/alpha-vantage.md).
- **Managed universe snapshot** — `POST /data/universe/sync` refreshes
  Instruments from Alpha Vantage listing-status data and
  `GET /data/universe` browses/searches the managed catalog with
  `AQP_DEFAULT_UNIVERSE` fallback when snapshots are empty.
- **Identifier graph** — `identifier_links` stores polymorphic,
  time-versioned aliases for every Instrument — ticker, vt_symbol,
  CIK, CUSIP, ISIN, FIGI, LEI, GVKEY, PermID, ... The
  `IdentifierResolver` upserts and reverse-looks-up through this graph
  and writes-through to the legacy `Instrument.identifiers` JSON blob
  so older readers stay compatible.
- **FRED** adapter — pulls economic series (DGS10, UNRATE,
  CPIAUCSL, ...) into the parquet lake with lineage. Install with
  `pip install -e ".[fred]"`, set `AQP_FRED_API_KEY`.
- **SEC EDGAR** adapter — powered by
  [edgartools](https://github.com/dgunning/edgartools). Indexes
  filings (`10-K`, `10-Q`, `8-K`, `4`, `13F-HR`, ...) and extracts
  standardised financials, insider transactions, and 13F holdings.
  Install with `pip install -e ".[sec]"`, set
  `AQP_SEC_EDGAR_IDENTITY`.
- **GDelt GKG 2.0** adapter — hybrid manifest (15-minute partitioned
  parquet lake) **and** BigQuery federation. Optional subject filter
  keeps only rows that mention a registered Instrument so a typical
  laptop can run it. Install with `pip install -e ".[gdelt]"` (and
  `".[gdelt-bq]"` for BigQuery).
- **Data availability API** — `GET /instruments/{vt_symbol}/data`
  aggregates `data_links` rows so the UI can answer "for AAPL we have
  bars from yfinance (2020-2024, 1206 rows), 12 10-K filings and 4392
  GDelt mentions".

See [docs/data-plane.md](docs/data-plane.md) for the full walkthrough,
CLI cheat sheet, and API reference.

## What's new in 0.5 — UI shell + workbenches + optimizer

- **Grouped-sidebar shell** — every page lives under one of six sections
  (Dashboard / Research / Data / Lab / Execution / Monitor). Section
  membership is declared once per route in
  [`aqp/ui/app.py`](aqp/ui/app.py) via a `data={"section": ...}` hint the
  new [`AppShell`](aqp/ui/layout/app_shell.py) + [`SectionNav`](aqp/ui/layout/section_nav.py)
  render into a collapsible sidebar. A top-bar carries live
  kill-switch + environment pills driven by `use_api`.
- **Shared component library** — [`aqp/ui/components/`](aqp/ui/components/)
  ships reusable pieces used across every page: `use_api` reactive hook
  with polling, `MetricTile` / `TileTrend`, `EntityTable`, `TaskStreamer`
  + `LiveStreamer` (real WebSocket clients over `/chat/stream/{id}` and
  `/live/stream/{id}` with polling fallback), `Candlestick` + multi-panel
  `IndicatorOverlay`, `Heatmap`, `StatsGrid`, `FormBuilder` (schema →
  widgets), `YamlEditor` (validate + diff + save), `ParameterEditor`
  (data-driven Alpha/Portfolio/Risk controls), `TabPanel`, `CardGrid`,
  `SplitPane`, `DashEmbed`.
- **Strategy Workbench** — the old 710-line `strategy.py` becomes a
  tabbed Build / YAML / Test / Versions / Results page
  ([`aqp/ui/pages/strategy.py`](aqp/ui/pages/strategy.py)) wired through
  `ParameterEditor` and `EquityCard`.
- **Factor Workbench** — [`aqp/ui/pages/factor_workbench.py`](aqp/ui/pages/factor_workbench.py)
  replaces Factor Evaluation with tabs for Evaluate / Formula Lab /
  Library. The Formula Lab is a live editor over
  [`aqp/data/expressions.py`](aqp/data/expressions.py); it hits the new
  `POST /factors/preview` and `GET /factors/operators` endpoints.
- **Indicator Builder** — new page
  ([`aqp/ui/pages/indicator_builder.py`](aqp/ui/pages/indicator_builder.py))
  that picks indicators from the Indicator Zoo and overlays them on a
  candlestick via `POST /data/indicators/preview` and
  `GET /data/indicators`.
- **Crew Trace** — dense swim-lane view of a running agentic crew
  ([`aqp/ui/pages/crew_trace.py`](aqp/ui/pages/crew_trace.py)) with a
  first-class registry (`GET /agents/crews[/{task_id}[/events]]`) and the
  live `TaskStreamer` WebSocket plugged straight into
  `/chat/stream/{task_id}`.
- **Optimizer Lab** — new sweep engine
  ([`aqp/backtest/optimizer.py`](aqp/backtest/optimizer.py)) + Celery
  task ([`aqp/tasks/optimize_tasks.py`](aqp/tasks/optimize_tasks.py)) +
  `OptimizationRun` / `OptimizationTrial` models (migration
  [`alembic/versions/0003_optimizer_and_crew.py`](alembic/versions/0003_optimizer_and_crew.py))
  + `POST /backtest/optimize`, `GET /backtest/optimize/{id}`,
  `GET /backtest/optimize/{id}/results`, and a tabbed UI
  ([`aqp/ui/pages/optimizer.py`](aqp/ui/pages/optimizer.py)) that renders
  results as a parameter heatmap.
- **Monte Carlo Lab** — [`aqp/ui/pages/monte_carlo.py`](aqp/ui/pages/monte_carlo.py)
  wraps the existing `/backtest/monte_carlo` task with a spaghetti
  preview built from the selected run's equity curve.
- **Paper Runs** — the long-invisible `/paper/runs` now has its own UI
  ([`aqp/ui/pages/paper_runs.py`](aqp/ui/pages/paper_runs.py)) with a
  list/detail split, a KPI strip per run, a Stop button, and a config
  launcher.
- **ML Models detail** — [`aqp/ui/pages/ml_model_detail.py`](aqp/ui/pages/ml_model_detail.py)
  opens any `ModelVersion` row and, through `GET /ml/models/{id}/details`,
  renders metrics, feature importance (bar chart + table), prediction
  samples, and dataset lineage.
- **ML planning + deployment slice** — reproducible split planning (`/ml/split-plans`),
  versioned preprocessing recipes (`/ml/pipelines`), experiment plans
  (`/ml/experiments`), deployment bindings (`/ml/deployments`), and
  `DeployedModelAlpha` wiring so tested models can be reused directly in
  strategy/backtest recipes.
- **Denser existing pages** — Data Browser, Live Market, Portfolio, API
  Playground, and Chat were all tightened to use the shared component
  library. Live Market now streams bars over the real
  `/live/stream/{channel_id}` WebSocket instead of the old polling loop.
- **UI regression tests** — [`tests/ui/`](tests/ui/) guards every page
  import under Solara's strict rules-of-hooks, covers the component
  exports + `ModelCatalog` / `TileTrend` / `IndicatorOverlay` behaviour,
  pins the new `/data/indicators`, `/factors/preview`, `/backtest/optimize`,
  `/agents/crews`, `/ml/models/{id}/details` endpoints, and locks down
  the `TaskStreamer` polling fallback.

## What's new in 0.4 — ML + Backtest + Strategy zoo

- **Three interchangeable backtest engines** — the default
  `EventDrivenBacktester` is now joined by `VectorbtEngine`
  ([`aqp/backtest/vectorbt_engine.py`](aqp/backtest/vectorbt_engine.py))
  and `BacktestingPyEngine`
  ([`aqp/backtest/bt_engine.py`](aqp/backtest/bt_engine.py)). Pick one
  via `backtest.engine: event|vectorbt|backtesting` in any YAML; the
  runner normalises them into the same `BacktestResult` shape. See
  [`docs/backtest-engines.md`](docs/backtest-engines.md).
- **Native qlib-style ML stack** in
  [`aqp/ml/`](aqp/ml/) — zero qlib runtime dep:
  `Model` / `ModelFT`, `DatasetH` / `TSDatasetH`, `DataHandler` /
  `DataHandlerLP` (raw / infer / learn views), `AQPDataLoader`,
  `Alpha158` + `Alpha360` feature factories (~50 DSL operators),
  processors (`CSZScoreNorm`, `CSRankNorm`, `Fillna`, `DropnaLabel`,
  `MinMaxNorm`), and recorders (`SignalRecord`, `SigAnaRecord`,
  `PortAnaRecord`). See [`docs/ml-framework.md`](docs/ml-framework.md).
- **Model zoo** — Tier A (shipping) covers tree (LightGBM, XGBoost,
  CatBoost, DoubleEnsemble), linear (Ridge / Lasso / NNLS / OLS),
  dense (DNN), sequence (LSTM, GRU, ALSTM, Transformer, Localformer,
  TCN, TabNet), and a Seq2Seq family ported from Stock-Prediction-
  Models (LSTM / GRU / VAE / Dilated-CNN / attention). Tier B scaffolds
  GATs / HIST / TRA / ADD / ADARNN / TCTS / SFM / Sandwich / KRNN /
  IGMTF so they register cleanly in the YAML registry.
- **Strategy zoo expansion** — 12+ new strategy files ported from
  `quant-trading-master`, `backtesting.py`, and
  `stock-analysis-engine-master`:
  `AwesomeOscillatorAlpha`, `HeikinAshiAlpha`, `DualThrustAlpha`,
  `ParabolicSARAlpha`, `LondonBreakoutAlpha`, `BollingerWAlpha`,
  `ShootingStarAlpha`, `RsiPatternAlpha`, `OilMoneyRegressionAlpha`,
  `SmaCross`, `Sma4Cross`, `TrailingATRAlpha`, `BaseAlgoExample`.
  Each ships with a matching YAML in `configs/strategies/`.
- **Strategy Browser UI** — new Solara page at `/strategy-browser`
  with tag / Sharpe / name filters, deep-links into the per-strategy
  MLflow experiment, plus a catalog of every code-available
  `IAlphaModel` class. New endpoints: `GET /strategies/browse`,
  `GET /strategies/browse/catalog`,
  `GET /strategies/{id}/experiment`. See
  [`docs/strategy-browser.md`](docs/strategy-browser.md).
- **ML training pipeline** — `POST /ml/train` enqueues a Celery task
  on the new `ml` queue that builds a `DatasetH` + `Model` from YAML,
  fits, runs the `SignalRecord` / `SigAnaRecord` / `PortAnaRecord`
  templates, and registers the pickled model in the MLflow Model
  Registry. UI: `/ml` (ML Training page).
- **MLflow wiring fixed** — `BacktestRun.mlflow_run_id` now populates
  on every run; each strategy gets its own MLflow experiment
  (`strategy/<id[:8]>`); the Celery task-prerun autolog skips tasks
  that manage their own runs so you no longer see doubled runs.
- **Extra indicators** — `Ichimoku`, `Supertrend`, `PivotPoints`,
  `HeikinAshiTransform`, `AroonUp` / `AroonDown` registered in
  `ALL_INDICATORS`. Optional `pandas-ta` bridge via
  `aqp.data.indicators_zoo.from_pandas_ta`.
- **Expanded expression DSL** — ~50 operators in
  [`aqp/data/expressions.py`](aqp/data/expressions.py) mirroring
  qlib's `OpsList`: `Var` / `Skew` / `Kurt` / `Slope` / `Rsquare` /
  `Resi` / `Quantile` / `Count` / `EMA` / `WMA` / `Cov` / `IdxMax` /
  `IdxMin` / `Gt` / `Ge` / `Lt` / `Le` / `Eq` / `Ne` / `And` / `Or` /
  `Not` / `Mask` / `If` / `Sign` / `Power`.
- **Qlib-style metrics** — `risk_analysis`, `indicator_analysis`,
  `turnover_report` ported into
  [`aqp/backtest/metrics.py`](aqp/backtest/metrics.py); invoked
  automatically by `PortAnaRecord`.

## What's new in 0.3 — Lean + ML4T deep expansion

- **Core type system** ports every major Lean value object: `Slice`,
  `TradeBar` / `QuoteBar` / `Tick`, `SubscriptionDataConfig`,
  `Resolution` / `TickType` / `DataNormalizationMode`, `SecurityHolding`,
  `Cash` / `CashBook`, `OrderTicket` + `OrderEvent`,
  `IndicatorBase<T>` + `RollingWindow<T>` with 25 built-in indicators,
  `MarketHoursDatabase`, and `MapFile` / `FactorFile`. See
  [`docs/core-types.md`](docs/core-types.md).
- **Data browser** page with per-symbol candlestick, gap report, and
  normalised multi-symbol overlay. Paired new endpoints
  `GET /data/{vt_symbol}/bars` and `GET /data/{vt_symbol}/stats`.
- **Live market page + feeds** (`/live/subscribe` / `/live/stream/{ch}`)
  bridging Alpaca, IBKR, and a deterministic simulator to Redis pub/sub.
- **Factor evaluation** (Alphalens-style IC / quantile / turnover),
  `MultipleTimeSeriesCV` / `PurgedKFold` / walk-forward cross-validators,
  and `XGBoostAlpha` / `LightGBMAlpha` with MLflow autolog. See
  [`docs/factor-research.md`](docs/factor-research.md).
- **Strategy lifecycle**: versioned strategies with save / test / diff
  via `POST /strategies/{id}/test` and a fully integrated Strategy
  Development page. See [`docs/strategy-lifecycle.md`](docs/strategy-lifecycle.md).
- **MLflow autolog** for Celery tasks + dedicated helpers for paper
  sessions, walk-forward runs, factor reports, strategy versions, and
  alpha training.
- **Extra portfolio models** (MVO / HRP / Risk-Parity / Black-Litterman),
  **VWAP & TWAP execution**, **trailing-stop / sector / per-security
  drawdown risk models**, and **fundamental + ETF-basket universe
  selection**.
- **Local simulation**: ``aqp backtest simulate --local-path
  /mnt/vendor/bars --format csv`` wires CSV/Parquet on a mounted drive
  straight into the same event-driven engine.

## Quick start

### 1. Prerequisites

- Docker + Docker Compose
- Python 3.11+
- [Ollama](https://ollama.com/) running locally (for the LLM). Ollama runs **natively on the host** so it can access the GPU.

```bash
# Pull your preferred model. Default is nemotron:latest, but any Ollama model works.
ollama pull nemotron
# Or a lighter model for smaller GPUs:
ollama pull llama3.2
```

### 2. Clone and configure

```bash
git clone https://github.com/yourname/agentic_quant_platform.git
cd agentic_quant_platform
cp .env.example .env
# Edit .env — at minimum, set AQP_LLM_MODEL to your Ollama model tag.
```

### 3. Bring up infrastructure

```bash
make up                 # starts redis, postgres, mlflow, chromadb
make bootstrap          # creates data dirs + applies DB migrations
```

### 4. Install Python package (for local CLI + UI)

```bash
pip install -e ".[dev]"
```

### 5. Ingest some data and index it

```bash
make ingest             # downloads a small universe (SPY, AAPL, MSFT, ...) via yfinance
make index              # indexes file metadata into ChromaDB for semantic discovery
```

### 6. Launch the UI and API

```bash
aqp api &               # FastAPI on :8000 (Dash monitor mounted at /dash)
aqp worker &            # Celery worker (all queues incl. paper)
aqp ui                  # Solara on :8765
```

Open http://localhost:8765. The landing **Dashboard** page shows live
platform KPIs (kill switch, backtest runs, paper sessions, broker venues)
and launch tiles into each of the six sidebar sections:

| Section | Pages |
|---|---|
| **Research** | Chat · Strategy Browser · Indicator Builder · Factor Workbench |
| **Data** | Data Explorer · Data Browser · Live Market |
| **Lab** | Strategy Workbench · Backtest Lab · Optimizer · Monte Carlo · ML Training · ML Models · RL Dashboard |
| **Execution** | API Playground · Paper Runs · Portfolio |
| **Monitor** | Strategy Monitor (Dash) · Crew Trace |

Try asking the Quant Assistant something like:

> *"Find me a mean-reversion strategy on low-volatility tech stocks and backtest it on 2023-2024."*

Hit **Run Crew** to kick off the full research crew and jump to the
**Crew Trace** page to watch per-agent swim lanes fill in live.

The Dash strategy monitor is now available at [http://localhost:8000/dash/](http://localhost:8000/dash/) — there's no longer a separate process on port 8050.

## Unified `aqp` CLI

Everything in the platform is reachable through a single Typer CLI::

```bash
aqp api                                                   # FastAPI + Dash mount
aqp ui                                                    # Solara multi-page UI
aqp worker --queues default,backtest,paper                # Celery worker
aqp beat                                                  # Celery beat
aqp dash --standalone --port 8050                         # Legacy standalone Dash
aqp paper run --config configs/paper/alpaca_mean_rev.yaml
aqp paper run --config configs/paper/alpaca_mean_rev.yaml --dry-run
aqp paper stop <task-id>
aqp paper list
aqp backtest run --config configs/strategies/mean_reversion.yaml
aqp data load --path /mnt/vendor/bars --format csv
aqp data ingest --symbols AAPL,MSFT
aqp data describe
aqp bootstrap
aqp health
```

The legacy console scripts (`aqp-backtest`, `aqp-bootstrap`, `aqp-train`, …) still work for backwards compatibility.

## Paper trading

AQP ships with a Lean-inspired async paper / live trading engine that runs the **same `IStrategy` object** that the backtester exercises — so research, paper, and live trading share one code path.

| Concrete adapter | Requires | What you get |
|---|---|---|
| `AlpacaBrokerage` + `AlpacaDataFeed` | `pip install -e ".[alpaca]"` + Alpaca paper keys | Live WebSocket bars (IEX or SIP) + paper orders |
| `InteractiveBrokersBrokerage` + `IBKRDataFeed` | `pip install -e ".[ibkr]"` + running TWS / IB Gateway | Real-time 5s bars + stocks/futures orders |
| `TradierBrokerage` + `RestPollingFeed` | `pip install -e ".[tradier]"` + Tradier sandbox token | Form-encoded REST orders + quote polling |
| `SimulatedBrokerage` + `DeterministicReplayFeed` | *(core)* | Dry-run against the local Parquet lake |
| `KafkaDataFeed` (any brokerage) | `pip install -e ".[streaming]"` + running Kafka + Flink pipeline | Consume normalized features + trading signals produced by the streaming platform |

Config-driven launch:

```bash
aqp paper run --config configs/paper/alpaca_mean_rev.yaml --dry-run
```

Recipes live under [`configs/paper/`](configs/paper/); see the [README](configs/paper/README.md) for the full credential flow.

Runtime controls:

- Start via `POST /paper/start` (returns a `task_id`); listen to `/chat/stream/<task_id>` for progress.
- Stop via `POST /paper/stop/{task_id}` (or `aqp paper stop <task_id>`) — publishes a Redis shutdown signal the session drains on.
- Engage the global kill switch via `POST /portfolio/kill_switch` — all paper sessions halt within one heartbeat and cancel open orders.
- Inspect runs via `GET /paper/runs` / `GET /paper/runs/{id}` — orders, fills, and ledger entries flow through the same tables the backtester uses so `/portfolio/*` endpoints work unchanged.

See [docs/paper-trading.md](docs/paper-trading.md) for the full walkthrough.

## Streaming platform (Kafka + Flink)

AQP integrates with a distributed streaming platform that ingests
live market data from IBKR + Alpaca, processes it with Apache Flink,
and exposes normalized features + signals back to strategies.

Components:

- `aqp.streaming.ingesters.IBKRIngester` -- 24/7 IBKR ingester covering
  `tickByTick`, `reqRealTimeBars`, `reqMktData` (delayed + live),
  `reqScannerSubscription`, and `reqContractDetails`.
- `aqp.streaming.ingesters.AlpacaIngester` -- 24/7 Alpaca ingester
  covering every WSS channel (`trades`, `quotes`, `bars`,
  `updatedBars`, `dailyBars`, `statuses`, `imbalances`, `corrections`,
  `cancelErrors`).
- Twelve canonical Avro schemas in
  [aqp/streaming/schemas/](aqp/streaming/schemas/).
- PyFlink jobs (dedupe / indicator compute / normalize + sink /
  scanner alert) maintained in the companion `rpi_kubernetes` repo.
- `aqp.trading.feeds.kafka_feed.KafkaDataFeed` -- the consumer side so
  strategies see Flink output via the existing `IMarketDataFeed`
  interface.

Bring it up locally:

```bash
docker compose --profile streaming up -d   # Kafka + IB Gateway + ingesters
aqp-stream-ingest --venue all              # (alternative: run ingester on host)
```

See [docs/streaming.md](docs/streaming.md) for the full architecture.

## Local-drive data loading

Point AQP at CSV or Parquet files on any mounted drive:

```bash
aqp data load --path /mnt/vendor/daily --format csv --tz US/Eastern
aqp data load --path /mnt/vendor/minute --format parquet --glob "*.parquet"
```

This normalises the files into the canonical tidy schema (`timestamp`,
`vt_symbol`, `open`, `high`, `low`, `close`, `volume`) and writes them to
the Parquet lake so the DuckDB view, Chroma indexing, backtest, and
paper-trading pipeline all pick them up automatically. For read-only
overlays (no copy), set `AQP_LOCAL_DATA_ROOTS=/mnt/a,/mnt/b` and the
DuckDB `bars` view will `UNION ALL` them in.

REST equivalent: `POST /data/load` with body `{source_dir, format, column_map?, tz?, glob?}`.

## Observability (OpenTelemetry)

Install the `otel` extra and point at a collector:

```bash
pip install -e ".[otel]"
export AQP_OTEL_ENDPOINT=http://localhost:4317
```

`docker compose up -d` now launches an OpenTelemetry Collector + Jaeger
sidecar. Browse traces at [http://localhost:16686](http://localhost:16686).

Instrumented out of the box:

- FastAPI request spans (auto-instrumented)
- Celery task spans (auto-instrumented)
- SQLAlchemy query spans
- HTTPX client spans (broker REST calls)
- Redis pub/sub spans
- Manual spans on `paper.session.run`, `paper.session.bar`, `broker.submit_order`, etc.

See [docs/observability.md](docs/observability.md) for sampling, custom
exporters, and troubleshooting.

## Kubernetes

Kustomize manifests live in [`deploy/k8s/`](deploy/k8s/):

```bash
kubectl apply -k deploy/k8s/overlays/dev
kubectl -n aqp-dev create secret generic aqp-broker-secrets \
  --from-literal=AQP_ALPACA_API_KEY=... \
  --from-literal=AQP_ALPACA_SECRET_KEY=...
```

The paper-trader runs as a single-replica `Deployment` with
`Recreate` strategy so stateful sessions never race. See the
[k8s README](deploy/k8s/README.md) for full instructions.

## Repository layout

```
agentic_quant_platform/
├── aqp/                     # main package
│   ├── cli/                 # unified `aqp` Typer CLI
│   ├── core/                # types, interfaces, registry, events
│   ├── data/                # DuckDB, ArcticDB, ChromaDB, ingestion (incl. local drives)
│   ├── llm/                 # Ollama/LiteLLM client, prompts, memory
│   ├── agents/              # CrewAI crew + tools
│   ├── strategies/          # Lean-style 5-stage framework (+ 12 new alphas)
│   ├── backtest/            # event-driven + vectorbt + backtesting.py engines
│   ├── ml/                  # native qlib-style Model/Dataset/Handler + Alpha158/360 + model zoo
│   │   ├── features/        # Alpha158DL, Alpha360DL
│   │   └── models/          # tree, linear, ensemble, torch/{DNN, LSTM, GRU, ALSTM, Transformer, TCN, TabNet, Localformer, GeneralPTNN, seq2seq, stubs}
│   ├── trading/             # async paper/live engine, brokerages, feeds
│   │   ├── brokerages/      # Alpaca, IBKR, Tradier (REST), Simulated
│   │   └── feeds/           # AlpacaDataFeed, IBKRDataFeed, RestPollingFeed
│   ├── observability/       # OpenTelemetry tracing + @traced decorator
│   ├── rl/                  # gym envs + SB3 adapter + trainer
│   ├── mlops/               # MLflow client, registry, lineage
│   ├── persistence/         # SQLAlchemy ledger (incl. PaperTradingRun)
│   ├── risk/                # manager, limits, kill switch
│   ├── api/                 # FastAPI app + routes (+ /ml, + /paper, + /dash mount)
│   ├── tasks/               # Celery tasks (incl. ml_tasks, paper_tasks)
│   ├── ws/                  # Redis pub/sub bridge
│   └── ui/                  # Solara multi-page app (17 pages across 6 sections)
│       ├── layout/          # AppShell + SectionNav + PageHeader (the grouped-nav shell)
│       ├── components/      # Shared library: data, charts, forms, layout primitives
│       ├── pages/           # Dashboard, Strategy/Factor Workbenches, Indicator Builder,
│       │                    # Optimizer, Monte Carlo, Paper Runs, Crew Trace, ML Models…
│       └── dash_app.py      # Dash strategy monitor (mounted at /dash/)
├── configs/                 # YAML recipes (strategies, agents, RL, paper)
├── deploy/
│   ├── k8s/                 # Kustomize manifests (base + overlays/{dev,prod})
│   └── otel/                # OTel Collector config
├── scripts/                 # bootstrap, download, index, train, backtest
├── tests/                   # smoke tests per layer
├── notebooks/               # quickstart + walkthroughs
├── docker-compose.yml
└── pyproject.toml
```

## Agent roles

| Role | Responsibility | Key tools |
|---|---|---|
| **Data Scout** | Discover and validate local datasets | `DirectoryReadTool`, `DuckDBQueryTool`, `ChromaSearchTool` |
| **Hypothesis Designer** | Formulate strategies from natural language | `DeepLLM`, `ChromaSearchTool` |
| **Strategy Backtester** | Simulate performance on historical data | `BacktestTool`, `WFOTool` |
| **Risk Controller** | Monitor exposure and enforce stop-losses | `RiskCheckTool`, `LedgerTool` |
| **Performance Evaluator** | Compute Sharpe, Sortino, Max Drawdown | `MetricsTool`, `PlotlyTool` |
| **Meta-Agent** | Monitor system-wide drift; can halt execution | `LedgerTool`, `KillSwitchTool` |

## Reinforcement Learning

AQP ships with FinRL-style gym environments and a thin Stable-Baselines3 adapter supporting **A2C, DDPG, PPO, SAC, and TD3**. Every training run is autologged to MLflow and tagged with a dataset-hash for reproducibility.

```bash
aqp-train --config configs/rl/ppo_portfolio.yaml
```

## Backtesting modes

- **Vectorized** (Pandas/NumPy) — rapid hypothesis screening.
- **Event-driven** — chronological tick/bar replay with slippage + commissions.
- **Walk-Forward Optimization (WFO)** — rolling in-sample / out-of-sample windows.
- **Monte Carlo** — randomised price paths to stress-test robustness.

## Configuration

AQP uses a layered config approach:

- `.env` (Pydantic Settings) — secrets and runtime flags.
- `configs/*.yaml` — Qlib-style recipes with `class` / `module_path` / `kwargs` triples resolved by `aqp.core.registry.build_from_config()`.

## Governance

- **Execution Ledger** in PostgreSQL records every signal, order, fill, and agent action.
- **Kill Switch** — the Meta-Agent (or an operator) can set `aqp:kill_switch` in Redis to instantly halt all strategies.
- **Lineage** — every trained model is linked to the SHA256 hash of its training dataset.
- **Data Sovereignty** — all inference runs on Ollama; no data leaves the host.

## License

MIT. See [LICENSE](LICENSE).
