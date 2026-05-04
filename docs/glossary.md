# Glossary

Project-specific jargon used across AQP, with a definition and a pointer
to the canonical file. New contributors and AI agents should treat this
as the **single source of truth** for terminology — if you find a
mismatch between this glossary and the code, file an issue.

> See also: [docs/index.md](index.md) for the full doc map.

## Core domain

- **`vt_symbol`** — Composite symbol id with the shape
  `{TICKER}.{EXCHANGE}` (vnpy convention), e.g. `AAPL.NASDAQ`,
  `BTCUSDT.BINANCE`, `ESM4.CME`. Always created via `Symbol.parse(...)` /
  `Symbol.format(...)` in [aqp/core/types.py](../aqp/core/types.py); never
  hand-split.
- **`Symbol`** — Immutable dataclass that bundles `ticker`, `exchange`,
  `asset_class`, `security_type`, optional contract spec. The atom
  flowing through every data feed, strategy, and broker. Defined in
  [aqp/core/types.py](../aqp/core/types.py).
- **`AssetClass` vs `SecurityType`** — `AssetClass` is the broad
  category (`equity`, `crypto`, `fx`, `future`, `option`, `index`,
  `commodity`, `bond`). `SecurityType` is the Lean-style finer-grained
  enum (`equity`, `option`, `future_option`, `crypto_future`,
  `index_option`, …). The `_polymorphic_identity_for` helper in
  [aqp/data/catalog.py](../aqp/data/catalog.py) maps `SecurityType` to a
  joined-table subclass of `Instrument`.
- **`Resolution`** — Lean-style bar cadence (`Tick`, `Second`, `Minute`,
  `Hour`, `Daily`); see [aqp/core/types.py](../aqp/core/types.py).
- **`Interval`** — Short-code bar cadence (vnpy style, `1m`, `5m`,
  `1h`, `1d`). Same idea as `Resolution`, kept for vnpy back-compat.
- **`SubscriptionDataConfig`** — The data-plane routing key. Combines
  `Symbol + Resolution + TickType + DataNormalizationMode`. See
  [docs/core-types.md](core-types.md).

## Persistence + data plane

- **Execution Ledger** — The Postgres tables under
  [aqp/persistence/models.py](../aqp/persistence/models.py) +
  [aqp/persistence/ledger.py](../aqp/persistence/ledger.py) that record
  every signal, order, fill, agent decision, and backtest run.
  Authoritative for "what did the system actually do?".
- **`LedgerWriter`** — Façade over the ledger tables. Always go through
  it instead of writing to ORM models directly so audit messages get
  emitted. [aqp/persistence/ledger.py](../aqp/persistence/ledger.py).
- **`Instrument` joined-table inheritance** — `instruments` is the
  parent table; each subclass (`InstrumentEquity`, `InstrumentOption`,
  …) lives in its own joined-table row keyed on `instruments.id`. The
  `instrument_class` discriminator selects the subclass at load time.
  See [docs/erd.md](erd.md) and
  [aqp/persistence/models_instruments.py](../aqp/persistence/models_instruments.py).
- **`polymorphic_identity`** — SQLAlchemy mapper arg that ties a
  subclass to a discriminator value (e.g.
  `InstrumentEquity.__mapper_args__ = {"polymorphic_identity": "spot"}`).
  When you add a new instrument subclass you must also extend the
  `mapping` dict in `_polymorphic_identity_for`.
- **`DatasetCatalog`** — Parent row describing a logical dataset
  (HMDA LAR, FDA device events, etc.) with provider/domain/tags.
- **`DatasetVersion`** — Per-materialisation row beneath
  `DatasetCatalog`. Captures row count, dataset hash, schema snapshot,
  Iceberg identifier.
- **`DataLink`** — Edge between a `DatasetVersion` and an entity
  (`Instrument`, `Issuer`, `EconomicSeries`). Use this for "which
  symbols does this dataset cover?" queries.
- **`DataSource`** — Logical provider record (Yahoo, Alpha Vantage,
  IBKR, openFDA). Datasets and data-links reference a `DataSource`.
- **`IcebergCatalog`** (the wrapper) — PyIceberg handle from
  [aqp/data/iceberg_catalog.py](../aqp/data/iceberg_catalog.py).
  Always go through `append_arrow`, `read_arrow`,
  `iceberg_to_duckdb_view`; never call PyIceberg's `Catalog.create_table`
  directly.
- **`aqp_<source>` namespace** — Iceberg namespace convention for the
  regulatory ingest:
  `aqp_cfpb`, `aqp_uspto`, `aqp_fda`, `aqp_sec`. New corpora pick a new
  `aqp_<source>` slug.
- **Persistent host warehouse** — `C:/aqp-warehouse` on Windows,
  bind-mounted into `aqp-api` and `aqp-worker` at `/warehouse`.
  Holds the PyIceberg SQL catalog (`catalog.db`), Parquet data files,
  staging dir, and ingest audit logs. See [docs/data-catalog.md](data-catalog.md).
- **`legacy` profile** — Docker Compose profile that bundles the older
  REST + MinIO catalog topology (off by default). Bring it up with
  `docker compose --profile legacy up -d`.

## Strategies + backtest

- **`BaseStrategy`** — Abstract strategy contract under
  [aqp/strategies/](../aqp/strategies/). Subclasses implement
  `on_bar`, `on_signal`, etc. See [docs/backtest-engines.md](backtest-engines.md).
- **`MLAlphaStrategy` / `MLSelectorAlpha`** — Strategies that wrap an
  ML model (deployed via `ModelDeployment`) and emit signals.
- **`EnsembleAlpha`** — Weighted combination of multiple alphas.
  [aqp/strategies/ml_alphas.py](../aqp/strategies/ml_alphas.py).
- **`IBrokerage` / `IDataQueueHandler`** — Lean-style interfaces
  consumed by backtest, paper, and live engines without modification
  (the same strategy code runs against all three). See
  [docs/paper-trading.md](paper-trading.md).
- **`BacktestRun`** — Postgres row describing one backtest invocation
  (Sharpe, Sortino, drawdown, MLflow run id, dataset hash). The
  backtest UI's history view is just a query against this table.
- **`MLflow run id`** — Foreign id stored on `BacktestRun.mlflow_run_id`
  pointing at the MLflow tracking server. Click-through from the UI
  opens the MLflow UI in a new tab.
- **`dataset_hash`** — Deterministic SHA-256 of the input bars used in
  a backtest. Lets the UI flag "two backtests with the same hash =
  identical inputs".

## ML + agents

- **Tier (`deep` / `quick`)** — Two LLM tiers in the agentic crews.
  `deep` = high-capability (Nemotron 70B / GPT-4-class) for analysis;
  `quick` = small/fast (Llama 3.2 / Mini) for control-flow decisions.
  Provider per tier is in `settings.llm_provider_deep` /
  `_quick`; model per tier in `llm_deep_model` / `llm_quick_model`.
- **`router_complete`** — One-shot LLM completion through LiteLLM
  exposed by [aqp/llm/providers/router.py](../aqp/llm/providers/router.py).
  All AQP code goes through this — never call `litellm.completion` or
  the Ollama client directly.
- **`Director`** — Nemotron-driven planner + verifier in
  [aqp/data/pipelines/director.py](../aqp/data/pipelines/director.py).
  Sits between discovery and materialisation in generic file ingestion.
- **`IngestionPlan` / `PlannedDataset`** — Director output dataclass.
  One `PlannedDataset` per discovered family with target namespace,
  table name, expected_min_rows, domain hint, and skip list.
- **`VerifierVerdict`** — Director's post-materialise judgement
  (`accept` or `retry` with adjusted knobs).
- **`__assets__` family** — Synthetic `DiscoveredDataset` carrying the
  non-tabular inventory (PDFs, XML, images) found during discovery.
  Never materialised; surfaced under
  `IngestionReport.extras` for visibility.
- **`AgentDecision` / `DebateTurn`** — Agent crew audit trail rows.
- **`CrewRun`** — One full agentic crew invocation (planner →
  research → execution sub-agents).
- **`Alpha158`** — Microsoft Qlib's 158-feature factor zoo, ported to
  AQP under [aqp/data/indicators_zoo.py](../aqp/data/indicators_zoo.py).
- **`FeatureSet` / `FeatureSetVersion`** — Composable feature spec
  (list of `IndicatorZoo` expressions + transformations) versioned
  in Postgres, materialised on demand.
- **`ModelDeployment` / `MLDeployment`** — A trained ML model that
  has been registered for inference (rows in
  [aqp/persistence/models.py](../aqp/persistence/models.py)).

## Bots

- **`Bot`** — Smallest self-contained, deployable unit on AQP.
  Aggregates a universe + data pipeline + strategy + backtest engine +
  optional ML deployments + optional agent specs + RAG plan + metrics
  + risk caps + deployment target. Lives under a `Project` and is
  uniquely identified by `(project_id, slug)`. See
  [docs/bots.md](bots.md).
- **`BotSpec`** — Pydantic blueprint for a bot. Hashed via
  `snapshot_hash()` to drive immutable `bot_versions` snapshots.
  Defined in [aqp/bots/spec.py](../aqp/bots/spec.py).
- **`TradingBot` / `ResearchBot`** — Bot subclasses selected by
  `BotSpec.kind`. `TradingBot` does backtest / paper / deploy;
  `ResearchBot` does chat (and optional backtest if a `strategy` block
  is set).
- **`BotRuntime`** — Single sanctioned execution entry point for any
  bot lifecycle action. Snapshots specs into `bot_versions`, opens
  `bot_deployments` rows, and emits progress through
  [aqp/tasks/_progress.py](../aqp/tasks/_progress.py).
- **`bot_versions`** — Immutable, hash-locked spec snapshots
  (mirrors `agent_spec_versions`). Never mutated in place.
- **`bot_deployments`** — Ledger of every backtest / paper / chat /
  k8s invocation for a bot. References the `BotVersion` that produced
  it so a run can be replayed.
- **Deployment target (`paper_session` / `kubernetes` /
  `backtest_only`)** — Selected via `BotSpec.deployment.target`.
  Backed by `aqp/bots/deploy.py::DeploymentDispatcher`.

## Provider catalog

- **`LLMProvider`** — Lightweight handle around a LiteLLM provider
  spec. Registered in
  [aqp/llm/providers/catalog.py::PROVIDERS](../aqp/llm/providers/catalog.py).
- **`ProviderSpec`** — Static config for a provider slug (LiteLLM
  prefix, env-var name, default models).
- **`vllm` provider** — OpenAI-compatible vLLM endpoint behind LiteLLM's
  `openai/` adapter. Empty `AQP_VLLM_BASE_URL` disables.
- **`nemotron-3-nano:30b`** — Default Director model on Ollama
  (NVIDIA Nemotron Nano v3, 31.6B params). Pull with
  `ollama pull nemotron-3-nano:30b`. Configurable via
  `AQP_LLM_DIRECTOR_MODEL`.

## Streaming + live

- **`KafkaDataFeed`** — In-process Kafka consumer that hands bars/quotes
  to the `IDataQueueHandler` interface.
- **`features.indicators.v1`, `market.bar.v1`, …** — Versioned Kafka
  topics. Naming pattern is `<domain>.<entity>.v<n>`.
- **`StreamingIngester`** — `aqp-stream-ingest` CLI that publishes
  to Kafka topics from Alpaca / IBKR.
- **Heartbeat / kill-switch** — Periodic Redis publish from the paper-
  trading session; absence triggers the runner to halt.
  `AQP_RISK_KILL_SWITCH_KEY` (default `aqp:kill_switch`).

## Observability

- **OTEL endpoint** — `AQP_OTEL_ENDPOINT` (default empty disables).
  When set, every Celery task and HTTP request emits OpenTelemetry
  spans via [aqp/observability/](../aqp/observability/).
- **Progress bus** — Redis pub/sub channel
  `aqp:task:<task_id>` carrying `{stage, message, timestamp, **extra}`
  payloads. UIs subscribe via the WebSocket relay at
  `/chat/stream/{task_id}`. See
  [aqp/ws/broker.py](../aqp/ws/broker.py) and
  [aqp/tasks/_progress.py](../aqp/tasks/_progress.py).

## Configuration

- **`settings`** — Cached `Settings` instance from
  [aqp/config.py](../aqp/config.py). Always import as
  `from aqp.config import settings` and never construct
  `Settings()` directly — the cache backs `lru_cache(maxsize=1)`.
- **`AQP_*` env namespace** — Every settable knob takes the
  `AQP_` prefix. Bools accept `true`/`false`/`1`/`0`. Paths are
  resolved by `_coerce_path`.
- **`host-downloads`** — `/host-downloads:ro` bind mount in
  `docker-compose.yml` exposing the user's local `Downloads/`
  directory for CLI ingest jobs.

## Inspiration rehydration (Phase 2026-04-29)

- **Microprice** — `(P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)`.
  Volume-weighted refinement of mid-price; converges to the deeper side
  of the book. Implemented in
  [aqp/data/microstructure.py](../aqp/data/microstructure.py).
- **OBI (Order Book Imbalance)** — `(Q_bid - Q_ask) / (Q_bid + Q_ask)`,
  range `[-1, +1]`. Positive = bid-side pressure. Used as a quote skew
  signal in the LOB market-making strategies under
  [aqp/strategies/hft/](../aqp/strategies/hft/).
- **VPIN** — Volume-synchronized probability of informed trading
  (Easley/López/O'Hara). Re-buckets trade flow by equal-volume buckets;
  rolling mean of |buy-sell|/|buy+sell|. See
  [aqp/data/microstructure.py](../aqp/data/microstructure.py).
- **Sample-aware Sharpe** — Annualised Sharpe ratio that uses the
  actual sample frequency of a returns series instead of the assumed
  252 trading days. Required for HFT strategies with sub-daily bars.
  See [aqp/backtest/hft_metrics.py](../aqp/backtest/hft_metrics.py).
- **Walk-forward** — Training scheme where the model is re-fit on a
  rolling (or anchored) window and tested on the immediately following
  slice. Implemented in
  [aqp/ml/walk_forward.py](../aqp/ml/walk_forward.py).
- **Bachelier (Normal) model** — Options pricing model assuming the
  underlying follows arithmetic Brownian motion (`dF = sigma dW`).
  Appropriate for low-priced or near-zero underlyings (rates, basis
  spreads). See [aqp/options/normal_model.py](../aqp/options/normal_model.py).
- **Inverse option** — Option settled in the underlying asset (e.g.
  BTC) rather than quote currency (USD). Common on crypto venues like
  Deribit. See
  [aqp/options/inverse_options.py](../aqp/options/inverse_options.py).
- **Regime classifier** — Lightweight classifier that labels each bar
  as trending vs ranging using ADX threshold (default 25) or as
  bull/bear/neutral via multi-MA slope vote. See
  [aqp/data/regime.py](../aqp/data/regime.py).
- **Factor expression** — Tiny Polars-based DSL covering Alpha101
  primitives (`Ts_Mean`, `Ts_Std`, `Rank`, `Decay_Linear`, `Delta`,
  `Ts_Corr`). See [aqp/data/factor_expression.py](../aqp/data/factor_expression.py).
- **Engle-Granger cointegration** — Two-step test for cointegrated
  pairs: OLS hedge ratio + ADF test on the residual. See
  [aqp/data/cointegration.py](../aqp/data/cointegration.py).
- **Triple-barrier label** — Lopez de Prado labeling: look forward
  ``horizon`` bars, label `+1` if upper barrier hit first, `-1` if
  lower, `0` if horizon reached. See
  [aqp/data/labels.py](../aqp/data/labels.py).
- **Yang-Zhang volatility** — OHLC vol estimator combining overnight,
  open-to-close, and Rogers-Satchell components. The most efficient of
  the OHLC family. See
  [aqp/data/realised_volatility.py](../aqp/data/realised_volatility.py).
- **LobStrategy** — ABC for limit-order-book strategies; subclasses
  emit `OrderIntent` lists in response to `LobState` updates. Engine
  integration is deferred — see
  [extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md](../extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md).
- **Dataset preset** — Curated declarative spec for a one-click
  ingestion (e.g. `intraday_momentum_etf`, `crypto_majors_intraday`).
  See [aqp/data/dataset_presets.py](../aqp/data/dataset_presets.py).
- **Inspiration source** — One of seven external repos under
  `inspiration/` from which strategies / models / agents were
  rehydrated. Tracked via the `source` kwarg on
  `aqp.core.registry.register` and surfaced as the `source:*` tag.

## Testing

- **`tests/data/test_pipelines_smoke.py`** — Reference test for the
  Iceberg ingestion path. New ingest features should add a test in
  this directory.
- **`director_enabled=False`** — Pass when constructing
  `IngestionPipeline` in tests so the real LLM is bypassed in favour
  of the deterministic identity plan.

## Cross-repo

- **`agentic_assistants`** — Sibling repo providing the cross-system
  lineage API (`AQP_AGENTIC_ASSISTANTS_API`).
- **`rpi_kubernetes`** — Sibling repo with the k8s deployment
  manifests under [deploy/k8s/](../deploy/k8s/).
