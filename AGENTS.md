# AGENTS.md

> **Agentic entry point** for the Agentic Quant Platform (AQP). Humans
> should start at [docs/architecture.md](docs/architecture.md). This
> file is a terse, deterministic rule-set — read it top-to-bottom
> before you make changes.

## Project map

Every subpackage under [aqp/](aqp/) with its purpose and canonical doc.
Use this as your first lookup when answering "where does X live?".

| Path | What lives here | Canonical doc |
| --- | --- | --- |
| [aqp/agents/](aqp/agents/) | CrewAI crews + spec-driven runtime + Research/Selection/Trader/Analysis teams | [docs/agents.md](docs/agents.md), [docs/agentic-pipeline.md](docs/agentic-pipeline.md) |
| [aqp/agents/graph/](aqp/agents/graph/) | LangGraph orchestration (state, builder, conditions, Redis checkpointer, decision log) | [docs/agents.md](docs/agents.md) |
| [aqp/api/](aqp/api/) | FastAPI app + 30+ route modules under `routes/` | [docs/architecture.md](docs/architecture.md) |
| [aqp/backtest/](aqp/backtest/) | Backtest engines (vbt-pro primary, event-driven, OSS vectorbt, backtesting.py, ZVT, AAT, fallback cascade); shared `BaseBacktestEngine` ABC + `EngineCapabilities` | [docs/backtest-engines.md](docs/backtest-engines.md) |
| [aqp/bots/](aqp/bots/) | **Bot entity** — smallest deployable unit (TradingBot / ResearchBot). Aggregates universe + strategy + engine + ML + agents + RAG + metrics; drives backtest / paper / chat / k8s deploy via `BotRuntime` | [docs/bots.md](docs/bots.md) |
| [aqp/backtest/vbtpro/](aqp/backtest/vbtpro/) | Deep vectorbt-pro integration (signals/orders/optimizer/holding/random modes, WFO via `Splitter`, `Param` sweeps, `IndicatorFactory` bridge) | [docs/vbtpro-integration.md](docs/vbtpro-integration.md) |
| [aqp/strategies/vbtpro/](aqp/strategies/vbtpro/) | vbt-pro-tuned alpha + order-model components (`AgenticVbtAlpha`, `MLVbtAlpha`, `AgenticOrderModel`) | [docs/vbtpro-integration.md](docs/vbtpro-integration.md) |
| [aqp/cli/](aqp/cli/) | `aqp` CLI commands | – |
| [aqp/core/](aqp/core/) | `Symbol`, enums, dataclasses, interfaces | [docs/core-types.md](docs/core-types.md) |
| [aqp/data/](aqp/data/) | Iceberg catalog wrapper, generic ingestion pipeline, indicator zoo | [docs/data-catalog.md](docs/data-catalog.md), [docs/data-plane.md](docs/data-plane.md) |
| [aqp/data/sources/{cfpb,fda,uspto}/](aqp/data/sources/) | Third-order regulatory adapters | [docs/regulatory-data.md](docs/regulatory-data.md) |
| [aqp/llm/](aqp/llm/) | Provider registry, LiteLLM router, Ollama client, BM25 + Redis hybrid memory | [docs/providers.md](docs/providers.md) |
| [aqp/ml/](aqp/ml/) | ML model factory, feature engineering, deployments, AlphaBacktestExperiment, lightweight workbench flows, adhoc helpers | [docs/ml-framework.md](docs/ml-framework.md), [docs/ml-libraries.md](docs/ml-libraries.md), [docs/ml-alpha-backtest.md](docs/ml-alpha-backtest.md), [docs/ml-flows.md](docs/ml-flows.md) |
| [aqp/mlops/](aqp/mlops/) | MLflow autolog hooks, lineage helpers | [docs/observability.md](docs/observability.md) |
| [aqp/observability/](aqp/observability/) | OTEL setup, tracers | [docs/observability.md](docs/observability.md) |
| [aqp/persistence/](aqp/persistence/) | SQLAlchemy ORM (15+ model files) + `LedgerWriter` | [docs/erd.md](docs/erd.md), [docs/data-dictionary.md](docs/data-dictionary.md) |
| [aqp/providers/](aqp/providers/) | Data-feed adapters (yfinance, AV, IBKR, …) | [docs/data-plane.md](docs/data-plane.md) |
| [aqp/rag/](aqp/rag/) | Hierarchical Redis RAG (Alpha-GPT levels × first/second/third-order corpora) | [docs/rag.md](docs/rag.md) |
| [aqp/risk/](aqp/risk/) | Position-, daily-, drawdown-loss limits | [docs/paper-trading.md](docs/paper-trading.md) |
| [aqp/rl/](aqp/rl/) | Metaclass-driven RL stack: core abstractions + envs (FinRL ports) + composable rewards / observations / actions / terminations + multi-framework agents (SB3 / ElegantRL / RLlib / CleanRL / LLM-hybrid) + data pipelines + ensemblers + experiments + Iceberg-backed trajectory store | [docs/rl-framework.md](docs/rl-framework.md), [docs/rl-lab.md](docs/rl-lab.md), [docs/rl-components.md](docs/rl-components.md), [docs/rl-iceberg.md](docs/rl-iceberg.md) |
| [aqp/rl/core/](aqp/rl/core/) | `RLComponent` metaclass + abstract bases (env, observation, action, reward, termination, policy, agent, data, ensembler, experiment, trajectory store) + JSON schema introspection | [docs/rl-framework.md](docs/rl-framework.md) |
| [aqp/rl/spec.py](aqp/rl/spec.py) + [aqp/rl/runtime.py](aqp/rl/runtime.py) | Hash-locked `RLExperimentSpec` + `RLRuntime` single sanctioned executor (mirrors `BotRuntime` / `AgentRuntime`) | [docs/rl-framework.md](docs/rl-framework.md) |
| [aqp/rl/trajectories/](aqp/rl/trajectories/) | Iceberg-backed trajectory persistence (`rl.trajectories`, `rl.equity_curves`, `rl.action_logs`, `rl.reward_decomposition`) + DuckDB views | [docs/rl-iceberg.md](docs/rl-iceberg.md) |
| [aqp/runtime/](aqp/runtime/) | Control-plane state (provider overrides, kill switches) | [docs/providers.md](docs/providers.md) |
| [aqp/services/](aqp/services/) | Higher-level domain services (Alpha Vantage, Tradier, …) | [docs/alpha-vantage.md](docs/alpha-vantage.md) |
| [aqp/strategies/](aqp/strategies/) | `BaseStrategy` + concrete alphas + framework | [docs/factor-research.md](docs/factor-research.md) |
| [aqp/streaming/](aqp/streaming/) | Kafka producers/consumers, IBKR + Alpaca ingesters | [docs/streaming.md](docs/streaming.md) |
| [aqp/streaming/admin/](aqp/streaming/admin/) | Native Kafka + Flink admin (AdminClient, FlinkSessionJob CRUD, Apicurio) | [docs/streaming-admin.md](docs/streaming-admin.md) |
| [aqp/streaming/producers/](aqp/streaming/producers/) | ProducerSupervisor + curated catalog | [docs/streaming-admin.md](docs/streaming-admin.md) |
| [aqp/streaming/templates/](aqp/streaming/templates/) | FlinkSessionJob manifest renderers (factor export) | [docs/streaming-admin.md](docs/streaming-admin.md) |
| [aqp/data/sinks/](aqp/data/sinks/) | Sink registry CRUD + version snapshots | [docs/data-pipelines-hub.md](docs/data-pipelines-hub.md) |
| [aqp/tasks/](aqp/tasks/) | Celery tasks (backtest / ingest / agents / paper / ml / rag / regulatory / etc) | (per consumer doc) |
| [aqp/trading/](aqp/trading/) | Paper trading session loop, broker abstractions | [docs/paper-trading.md](docs/paper-trading.md) |
| [aqp/ui/](aqp/ui/) | **Legacy Solara UI** — under `legacy` profile only | – |
| [aqp/utils/](aqp/utils/) | Cross-cutting helpers (key derivation, etc) | – |
| [aqp/ws/](aqp/ws/) | Redis pub/sub bridge + WebSocket helpers | – |

External code:

| Path | Purpose |
| --- | --- |
| [webui/](webui/) | Legacy Next.js 15 webui on `:3000`. Canonical operator UI until the [frontend/](frontend/) rewrite reaches parity. See [frontend/CUTOVER.md](frontend/CUTOVER.md). |
| [frontend/](frontend/) | Vite 7 + React 19 + Tailwind 4 + shadcn/ui rewrite on `:3001`. Phase 0 + Phase 1 ship today (Live Trading Desk, Action Center, kill-switch, sandbox banner, throttled WS pipeline, lightweight-charts WebGL OHLC, CodeMirror IDE). Remaining ~120 routes progressively port in phases 2-6. |
| [alembic/versions/](alembic/versions/) | DB migrations (immutable once shipped) |
| [deploy/k8s/](deploy/k8s/) | Kubernetes manifests for the rpi_kubernetes cluster |
| [scripts/](scripts/) | Operational scripts (`iceberg_smoke.py`, `ingest_regulatory.py`, …) |
| [configs/](configs/) | YAML configs (strategies, agents, ML models, LLM profiles, RAG taxonomies) |
| [tests/](tests/) | pytest suite |

## Hard rules

These hold across the codebase. Any PR that violates one will be sent back.

1. **All symbols are `Symbol` instances; symbol IDs are `vt_symbol`
   strings.** Never hand-split a `vt_symbol` on `.`. Use
   `Symbol.parse(vt_symbol)` from
   [aqp/core/types.py](aqp/core/types.py).
2. **All LLM calls go through `router_complete`** in
   [aqp/llm/providers/router.py](aqp/llm/providers/router.py). Don't
   call `litellm.completion`, `OllamaClient`, or vendor SDKs
   directly.
3. **All Iceberg writes go through
   `iceberg_catalog.append_arrow`** in
   [aqp/data/iceberg_catalog.py](aqp/data/iceberg_catalog.py). Don't
   call PyIceberg's `Catalog.create_table` / `Table.append` directly.
4. **All progress emits go through
   [aqp/tasks/_progress.py](aqp/tasks/_progress.py)**:
   `emit(task_id, stage, message, **extras)`,
   `emit_done(task_id, result)`, `emit_error(task_id, error)`.
   Don't publish to Redis from your task code.
5. **All cross-task state goes through Postgres.** Celery tasks must
   be idempotent and re-runnable.
6. **Migrations are immutable once committed.** Add a new migration
   under [alembic/versions/](alembic/versions/); never edit a shipped
   one. Migrations follow the `00NN_<short_slug>.py` naming
   convention.
7. **Configuration is read once via
   `from aqp.config import settings`.** Don't construct
   `Settings()` directly — there's an `lru_cache(maxsize=1)` backing
   it. Add new knobs as fields on `Settings` in
   [aqp/config.py](aqp/config.py); they pick up `AQP_*` env vars
   automatically.
8. **Strategies use the `class` / `module_path` / `kwargs` factory
   pattern** (Qlib-style) for instantiation from YAML. The registry
   is in [aqp/core/registry.py](aqp/core/registry.py); decorate new
   classes with `@register("MyClass")`.
9. **Logging uses `logging.getLogger(__name__)`** at module top.
   Don't use `print` outside scripts/.
10. **Tests live next to similar tests** under [tests/](tests/) and
    must run hermetically (no host filesystem outside the test, no
    network unless monkey-patched).
11. **All RAG retrievals + writes go through
    [aqp/rag/HierarchicalRAG](aqp/rag/hierarchy.py).** Don't query
    Redis vector indexes directly; don't write embeddings outside
    [aqp/rag/indexers/](aqp/rag/indexers/). Adding a new corpus = new
    indexer + new entry in [aqp/rag/orders.py](aqp/rag/orders.py)'s
    `OrderCatalog`.
12. **All spec-driven agent runs go through
    [aqp/agents/runtime.py::AgentRuntime](aqp/agents/runtime.py).**
    Telemetry, guardrails, cost caps, and `agent_runs_v2` rely on it.
    Don't call `router_complete` directly inside an agent module —
    declare the model in `AgentSpec.model` and let the runtime drive
    the call.
13. **`agent_spec_versions` rows are immutable, hash-locked.** Never
    update them in place. Re-snapshotting a changed spec creates a new
    version row automatically via
    [aqp/agents/registry.py::persist_spec](aqp/agents/registry.py).
14. **All bot lifecycle actions go through
    [aqp/bots/runtime.py::BotRuntime](aqp/bots/runtime.py).** Telemetry,
    `bot_versions` snapshots, and `bot_deployments` rows depend on it.
    Don't call `run_backtest_from_config` / `build_session_from_config`
    / `AgentRuntime` directly from a bot subclass — derive the cfg in
    `BaseBot._derive_*_cfg` and let the runtime drive the call.
15. **`bot_versions` rows are immutable, hash-locked.** Snapshotting via
 [aqp/bots/registry.py::persist_spec](aqp/bots/registry.py) creates a
 new version row automatically when the spec hash changes.
16. **All RL training / evaluation / paper-trading / replay /
 walk-forward goes through
 [aqp/rl/runtime.py::RLRuntime](aqp/rl/runtime.py).** Celery tasks
 (`aqp.tasks.rl_tasks`) and API routes (`aqp.api.routes.rl`) wrap it —
 they never call `agent.train` directly.
17. **`rl_experiment_versions` rows are immutable, hash-locked.**
 Re-snapshotting via
 [aqp/rl/registry.py::persist_spec](aqp/rl/registry.py) inserts a new
 version row automatically when the spec hash changes.
18. **All RL trajectory / equity-curve / action-log / reward-term
 writes go through
 [aqp/rl/trajectories/iceberg_writer.py::IcebergTrajectoryStore](aqp/rl/trajectories/iceberg_writer.py)**
 → [`iceberg_catalog.append_arrow`](aqp/data/iceberg_catalog.py). Don't
 call PyIceberg directly from RL code.
19. **All concrete RL components register through the
 [`RLComponent`](aqp/rl/core/base.py) metaclass.** Set ``rl_kind`` to
 one of the canonical kinds (`rl_env`, `rl_reward`, `rl_observation`,
 `rl_action`, `rl_termination`, `rl_policy`, `rl_agent`, `rl_data`,
 `rl_ensembler`, `rl_experiment`, `rl_trajectory_store`); the
 metaclass calls
 [`@register`](aqp/core/registry.py) automatically.
20. **LLM calls inside `LLMHybridAgent` route through
 [`router_complete`](aqp/llm/providers/router.py).** No direct
 `litellm.completion` / `OllamaClient` from RL code.
21. **New Iceberg tables that an agent will read MUST declare a
 medallion layer + business metadata.** Use
 [`aqp.data.catalog.register_dataset`](aqp/data/catalog/active_metadata.py)
 or pass `medallion_layer="bronze|silver|gold"` +
 `business_metadata=BusinessMetadata(...)` straight to
 [`iceberg_catalog.append_arrow`](aqp/data/iceberg_catalog.py).
 Bronze namespaces are `aqp_bronze_*`, Silver `aqp_silver_*`, Gold
 `aqp_gold_*`. The wrapper validates that the namespace prefix
 matches the declared layer. Read
 [docs/data-layer-unification.md](docs/data-layer-unification.md).
22. **Agents MUST NOT read Postgres / Iceberg directly.** Every
 catalog / dataset / entity / pipeline read from agent code goes
 through a registered
 [`DataMCPTool`](aqp/data/mcp/base.py). New agent reads = new
 `DataMCPTool` subclass under
 [aqp/data/mcp/tools/](aqp/data/mcp/tools/) — never an `import` of
 ORM models inside an agent body. The bridge auto-installs every
 `DataMCPTool` into [`TOOL_REGISTRY`](aqp/agents/tools/__init__.py)
 and the same catalog is exposed externally via the FastAPI router
 at `/mcp/data` and the `aqp-data-mcp` stdio binary. Read
 [docs/data-mcp.md](docs/data-mcp.md).

## Common workflows

```bash
# Bring up the stack (default profile)
docker compose up -d

# Run all tests
docker exec aqp-api python -m pytest

# Run only the data-pipeline test suite
docker exec aqp-api python -m pytest tests/data/

# Apply a new alembic migration
docker exec aqp-api alembic upgrade head

# Ingest the four regulatory corpora end-to-end
docker exec aqp-api python -m scripts.ingest_regulatory --no-annotate

# Refresh the L0 alpha base + entire RAG hierarchy
curl -XPOST http://localhost:8000/rag/refresh-l0
curl -XPOST http://localhost:8000/rag/refresh-hierarchy

# Verify Iceberg persistence after restart
docker exec aqp-api python -m scripts.iceberg_smoke --inspect-only

# Tail a Celery task's progress
docker exec aqp-api python -c "from aqp.ws.broker import subscribe; \
  [print(m) for m in subscribe('<task_id>')]"

# Recover from a busted migration
docker exec aqp-api alembic downgrade -1
# fix the migration file, then:
docker exec aqp-api alembic upgrade head
```

## Where to look for X

| If you need to … | Look in / start with |
| --- | --- |
| Add an API route | [aqp/api/routes/](aqp/api/routes/) — copy an existing module, register in [aqp/api/main.py](aqp/api/main.py) |
| Add a Celery task | [aqp/tasks/](aqp/tasks/) — pick the right file, decorate with `@celery_app.task(bind=True, name=...)`, register in [aqp/tasks/celery_app.py](aqp/tasks/celery_app.py)'s `include` list, route via `task_routes` |
| Add an LLM provider | One dict entry in [aqp/llm/providers/catalog.py::PROVIDERS](aqp/llm/providers/catalog.py); the router does the rest |
| Add an ML model | Implement in [aqp/ml/models/](aqp/ml/models/) following the `class`/`module_path`/`kwargs` pattern; decorate with `@register("Name", kind="model")`; add a YAML example in [configs/ml/](configs/ml/) and update [docs/ml-libraries.md](docs/ml-libraries.md) |
| Add a workbench flow | Implement `run_<flow>_flow(...)` in [aqp/ml/flows.py](aqp/ml/flows.py); register it in `run_flow(...)` and `list_flows()` so the webui drawer picks it up automatically; document in [docs/ml-flows.md](docs/ml-flows.md) |
| Add an ML preprocessor pipeline node | Subclass [aqp/ml/processors.py::Processor](aqp/ml/processors.py); reference the new class from [aqp/data/fetchers/transforms/ml_preprocessing.py](aqp/data/fetchers/transforms/ml_preprocessing.py) (umbrella node) or add a thin specialised tile via `_make_single_processor_node` |
| Run an alpha-backtest experiment | Use [aqp/ml/alpha_backtest_experiment.py::AlphaBacktestExperiment](aqp/ml/alpha_backtest_experiment.py) (or `POST /ml/alpha-backtest-runs`). Trains + registers + deploys + backtests + persists to `ml_alpha_backtest_runs` in one call. See [docs/ml-alpha-backtest.md](docs/ml-alpha-backtest.md) |
| Add a test workbench mode | Extend [aqp/tasks/ml_test_tasks.py](aqp/tasks/ml_test_tasks.py) with the new task and route it via [aqp/api/routes/ml.py](aqp/api/routes/ml.py); add a tab to [webui/components/ml/MlTestPage.tsx](webui/components/ml/MlTestPage.tsx) |
| Add a data source | Implement adapter in [aqp/providers/](aqp/providers/) or [aqp/services/](aqp/services/); register in [aqp/persistence/models.py::DataSource](aqp/persistence/models.py); document in [docs/data-plane.md](docs/data-plane.md) |
| Add a regulatory data adapter | Mirror [aqp/data/sources/cfpb/](aqp/data/sources/cfpb/) — client + adapter + catalog upserts + Celery task in [aqp/tasks/regulatory_tasks.py](aqp/tasks/regulatory_tasks.py) + REST route + RAG indexer in [aqp/rag/indexers/](aqp/rag/indexers/) |
| Add a persistence model | Add the class to the right `aqp/persistence/models_*.py` file; create an Alembic migration; update [docs/data-dictionary.md](docs/data-dictionary.md) and the relevant ERD section in [docs/erd.md](docs/erd.md) |
| Add a strategy | Subclass `IStrategy` (or use `FrameworkAlgorithm`) in [aqp/strategies/](aqp/strategies/); decorate with `@register("Name")`; YAML config under [configs/strategies/](configs/strategies/) |
| Add a backtest engine | Subclass [aqp/backtest/base.py::BaseBacktestEngine](aqp/backtest/base.py); declare an `EngineCapabilities` class attribute; decorate with `@register("Name")`; add a shortcut to [aqp/backtest/runner.py::_ENGINE_SHORTCUTS](aqp/backtest/runner.py) and document in [docs/backtest-engines.md](docs/backtest-engines.md) |
| Add a bot | Drop a YAML under [configs/bots/trading/](configs/bots/trading/) or [configs/bots/research/](configs/bots/research/); the registry auto-loads on first lookup. Programmatic: `BotSpec(...)` + `add_spec(spec)`. CRUD via `POST /bots`; lifecycle via `/bots/{id}/{backtest|paper|chat|deploy}`. |
| Add a bot deployment target | Subclass [aqp/bots/deploy.py::DeploymentTarget](aqp/bots/deploy.py); register on `DeploymentDispatcher.register(target)`; add the kind to the `BOT_PALETTE` Deploy section in [webui/components/bots/botPalette.ts](webui/components/bots/botPalette.ts). |
| Add an RL component (env / reward / observation / action / termination / policy / agent / data / ensembler / experiment / trajectory_store) | Subclass the matching base in [aqp/rl/core/](aqp/rl/core/) and set `rl_kind` + `rl_alias`. The [`RLComponent`](aqp/rl/core/base.py) metaclass auto-registers via `@register`. Add a palette tile in [webui/components/rl/palette.ts](webui/components/rl/palette.ts) and a serialiser entry in [webui/components/rl/serialize.ts](webui/components/rl/serialize.ts). |
| Add an RL reward term | Subclass [`RewardTerm`](aqp/rl/core/reward.py) in [aqp/rl/rewards/](aqp/rl/rewards/); add to [aqp/rl/rewards/__init__.py](aqp/rl/rewards/__init__.py); ship a sample composite YAML under [configs/rl/rewards/](configs/rl/rewards/) |
| Add an RL framework adapter | Subclass [`BaseRLAgent`](aqp/rl/core/policy.py) in [aqp/rl/agents/](aqp/rl/agents/); set `rl_alias`/`rl_source`; expose via the agents `__init__.py` (suppress import errors so the dep stays optional). |
| Add an RL data source | Subclass [`BaseDataPipeline`](aqp/rl/core/data.py) in [aqp/rl/data_pipelines/](aqp/rl/data_pipelines/); implement `download_data` / optionally override `add_risk_features` and `df_to_array`; add a YAML under [configs/rl/data_pipelines/](configs/rl/data_pipelines/). |
| Add an RL experiment / ensemble | Subclass [`BaseExperiment`](aqp/rl/core/experiment.py) / [`BaseEnsembler`](aqp/rl/core/ensembler.py) and ship under [aqp/rl/experiments/](aqp/rl/experiments/) / [aqp/rl/ensemblers/](aqp/rl/ensemblers/). |
| Run an RL experiment | Author / load an `RLExperimentSpec`, call `RLRuntime(spec).train(...)`. The runtime persists Iceberg trajectories + a `rl_runs` ledger row + MLflow artifacts. From the UI: [`/rl/lab`](webui/app/(shell)/rl/lab/page.tsx) → "Save & train". |
| Add a vbt-pro mode / kwarg | Extend [aqp/backtest/vbtpro/engine.py::VectorbtProEngine](aqp/backtest/vbtpro/engine.py); update [docs/vbtpro-integration.md](docs/vbtpro-integration.md) |
| Add an agent-aware alpha (vbt-pro) | Subclass `IAlphaModel` in [aqp/strategies/vbtpro/](aqp/strategies/vbtpro/); implement `generate_panel_signals` for the fast path; decorate with `@register("Name", kind="alpha")` |
| Add a per-bar agent dispatcher consumer | Strategy reads `context["agents"]` (the [aqp/strategies/agentic/agent_dispatcher.py::AgentDispatcher](aqp/strategies/agentic/agent_dispatcher.py)) and calls `consult(spec_name, inputs, ttl=...)` from `on_bar` — only works on `EventDrivenBacktester` |
| Add a feature / indicator | [aqp/data/indicators_zoo.py](aqp/data/indicators_zoo.py) — append to the spec map |
| Add a RAG corpus | One entry in [aqp/rag/orders.py::OrderCatalog](aqp/rag/orders.py); one new indexer in [aqp/rag/indexers/](aqp/rag/indexers/); register in `INDEXER_REGISTRY` |
| Add a spec-driven agent | One YAML in [configs/agents/](configs/agents/) (or in-code `AgentSpec` + `add_spec`); the registry auto-loads on first lookup |
| Add a tool | Subclass `crewai.tools.BaseTool` in [aqp/agents/tools/](aqp/agents/tools/), register in `TOOL_REGISTRY` |
| Add a test | Mirror the source path under [tests/](tests/); use the existing fixtures |
| Inspect Iceberg catalog | `from pyiceberg.catalog import load_catalog; load_catalog("aqp", type="sql", uri="sqlite:///C:/aqp-warehouse/iceberg/catalog.db", warehouse="file:///C:/aqp-warehouse/iceberg")` |
| Find every place a task is dispatched | `rg "<task_module>\.<task_name>\.delay\(" aqp/` |
| Find every config knob | [aqp/config.py](aqp/config.py) (single source of truth) |
| Add an inspiration-rehydrated asset | Decorate with `@register("Name", source="<repo>", category="<bucket>")` from [aqp/core/registry.py](aqp/core/registry.py); add a per-asset note to `extractions/<source>/REFERENCE.md`; ship a YAML under `configs/<kind>/<source>/<name>.yaml` |
| Choose a medallion layer | Use `aqp_bronze_<source>` for raw, `aqp_silver_<source>` for normalised, `aqp_gold_<entity>` for products. Validate with `medallion_layer="bronze\|silver\|gold"` on [`iceberg_catalog.append_arrow`](aqp/data/iceberg_catalog.py). Read [docs/data-layer-unification.md](docs/data-layer-unification.md) |
| Add a normalization strategy | Subclass [`BaseNormalizationStrategy`](aqp/data/normalization/base.py) in [aqp/data/normalization/strategies.py](aqp/data/normalization/strategies.py); decorate with `@register_normalization_strategy("alias")`; reference in `Silver` transform nodes |
| Add a DataMCP tool | Subclass [`DataMCPTool`](aqp/data/mcp/base.py) under [aqp/data/mcp/tools/](aqp/data/mcp/tools/), decorate with `@register_data_mcp_tool`. The bridge auto-installs into [`TOOL_REGISTRY`](aqp/agents/tools/__init__.py); the FastAPI router and stdio binary expose it externally. Read [docs/data-mcp.md](docs/data-mcp.md) |
| Add an entity-centric data product | Subclass [`BaseDataProduct`](aqp/data/products/base.py) under [aqp/data/products/](aqp/data/products/); add a matching `data.entities.*` MCP tool and a `/data/entities/...` REST route. Read [docs/data-products.md](docs/data-products.md) |
| Register active metadata | Call [`aqp.data.catalog.register_dataset`](aqp/data/catalog/active_metadata.py) with `medallion_layer`, `BusinessMetadata`, and an optional `DataContract` — or attach `@dataset(...)` to a fetcher / sink class for auto-upsert |
| Walk lineage | UI: [/data/hub](webui/app/(shell)/data/hub/page.tsx) Overview tab. API: `GET /data-control/lineage`. Agents: `data.catalog.lineage` MCP tool. Code: [aqp/data/catalog/lineage.py](aqp/data/catalog/lineage.py) |
| Add a microstructure feature | [aqp/data/microstructure.py](aqp/data/microstructure.py) — append a function and add to `__all__` |
| Add an OHLC vol estimator | [aqp/data/realised_volatility.py](aqp/data/realised_volatility.py) |
| Add a label generator | [aqp/data/labels.py](aqp/data/labels.py) |
| Add a portfolio construction model | [aqp/strategies/portfolio_construction.py](aqp/strategies/portfolio_construction.py); decorate with `@register("Name", kind="portfolio")` |
| Add a dataset preset | One entry in [aqp/data/dataset_presets.py::PRESETS](aqp/data/dataset_presets.py) + a Celery task in [aqp/tasks/dataset_preset_tasks.py](aqp/tasks/dataset_preset_tasks.py) + dispatch entry in `_TASKS_BY_PRESET` |
| Add a sink kind | One [`SinkKindDescriptor`](aqp/data/fetchers/sinks/__init__.py) entry, one `SinkNode` subclass under [aqp/data/fetchers/sinks/](aqp/data/fetchers/sinks/) decorated with `@register_node("sink.<kind>")`, document in [docs/data-pipelines-hub.md](docs/data-pipelines-hub.md) |
| Add a source setup wizard | Append to [`WIZARDS`](aqp/data/sources/setup_wizards.py); steps + runners; surfaced via `/sources/wizards` and the SourceSetupWizardModal UI |
| Add a Kafka admin endpoint | Extend [`NativeKafkaAdmin`](aqp/streaming/admin/kafka_admin.py); add a route in [aqp/api/routes/kafka.py](aqp/api/routes/kafka.py); update [docs/streaming-admin.md](docs/streaming-admin.md) |
| Add a Flink admin endpoint | Extend [`FlinkRestClient`](aqp/streaming/admin/flink_admin.py) or [`FlinkSessionJobK8s`](aqp/streaming/admin/flink_admin.py); add a route in [aqp/api/routes/flink.py](aqp/api/routes/flink.py) |
| Add a producer kind | One [`ProducerSpec`](aqp/streaming/producers/catalog.py) entry; the supervisor seeds it on next boot. Custom logic goes in [`ProducerSupervisor`](aqp/streaming/producers/supervisor.py) |
| Link a dataset to a Kafka topic / Flink job | `POST /datasets/{id}/streaming-links` with `{kind, target_ref, direction}` — the [refresh_links](aqp/tasks/streaming_link_tasks.py) Celery task can also infer them by naming convention |
| Schedule a manifest or dataset config | `POST /data-control/schedules` — writes through to the ORM and re-renders the Celery beat schedule via [aqp/tasks/scheduling.py](aqp/tasks/scheduling.py) |
| Use the dataset-loading agent | `POST /agents/dataset-loading/consult` — driven by [`AgentRuntime`](aqp/agents/runtime.py) and the [dataset_loading_assistant](configs/agents/dataset_loading_assistant.yaml) spec |
| Add a factor expression primitive | [aqp/data/factor_expression.py::_FUNCS](aqp/data/factor_expression.py) |
| Add an HFT metric | [aqp/backtest/hft_metrics.py](aqp/backtest/hft_metrics.py) — and surface in `hft_summary()` if appropriate |
| Add a chart-pattern detector | [aqp/data/patterns.py](aqp/data/patterns.py) — call from `detect_all` |
| Wire a future LOB strategy | Subclass [aqp/strategies/lob.py::LobStrategy](aqp/strategies/lob.py); engine integration in [extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md](extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md) |

## Don't list

Things that look like they should work but actively break the system.

- **Don't edit a shipped Alembic migration.** Add a new one.
- **Don't create a new `Settings()`.** Always use
  `from aqp.config import settings`.
- **Don't pickle ORM objects across tasks.** Pass IDs, re-fetch in
  the worker.
- **Don't call `litellm.completion` / `ollama.Client.generate`.** Use
  `router_complete`.
- **Don't write to Iceberg via raw PyIceberg.** Use the
  [aqp/data/iceberg_catalog.py](aqp/data/iceberg_catalog.py) wrapper.
- **Don't add new strategies/models without `@register("Name")`.**
  YAML loaders will fail silently.
- **Don't put strategy logic in API routes.** Routes thin-wrap
  Celery tasks; Celery tasks thin-wrap functions in `aqp/<pkg>/`.
- **Don't put Celery imports at module top-level inside FastAPI route
  files** — circular import risk. Inline the import inside the route
  function.
- **Don't read from `os.environ` directly.** Add the key to
  `Settings`, then read `settings.foo`.
- **Don't break the SSE/WebSocket payload shape.** Frames are
  `{task_id, stage, message, timestamp, **extra}` — extending is
  fine; renaming keys is not.
- **Don't store credentials in `.env`** outside what's already in
  [.env.example](.env.example). Use the
  [aqp/utils/keys.py](aqp/utils/keys.py) helpers for derivation when
  needed.
- **Don't introduce new diagram formats.** Mermaid only.
- **Don't add a hosted docs site (MkDocs / Sphinx).** GitHub renders
  markdown + mermaid natively; the docs work as-is.
- **Don't query Redis vector indexes directly.** Go through
  [aqp/rag/HierarchicalRAG](aqp/rag/hierarchy.py).
- **Don't write embeddings outside [aqp/rag/indexers/](aqp/rag/indexers/).**
  Adding a new source means adding a new indexer + corpus entry.
- **Don't replace [aqp/data/chroma_store.py](aqp/data/chroma_store.py).**
  Chroma stays for the dataset/code metadata indexes; Redis is for the
  hierarchical agent RAG.
- **Don't mutate `agent_spec_versions` rows.** They are immutable,
  hash-locked snapshots.
- **Don't bypass [aqp/agents/runtime.py::AgentRuntime](aqp/agents/runtime.py)
  for spec-driven agents.** Telemetry / guardrails / cost caps depend
  on it.
- **Don't call `router_complete` from inside an agent body.** Express
  the model choice via `AgentSpec.model` and let the runtime drive it.
- **Don't write decision/episode/reflection rows to Redis from agent
  code.** Use [aqp/llm/memory.py::RedisHybridMemory](aqp/llm/memory.py).
- **Don't bypass [aqp/bots/runtime.py::BotRuntime](aqp/bots/runtime.py)
  for bot lifecycle actions.** Telemetry / `bot_versions` snapshots /
  `bot_deployments` rows depend on it.
- **Don't mutate `bot_versions` rows.** They are immutable, hash-locked
  snapshots — re-snapshotting a changed spec creates a new version row.
- **Don't put backtest / strategy / engine / agent logic inside a Bot
  subclass.** Bots compose references and dispatch to existing
  primitives (`run_backtest_from_config`, `build_session_from_config`,
  `AgentRuntime`, `HierarchicalRAG`).
- **Don't bypass [aqp/rl/runtime.py::RLRuntime](aqp/rl/runtime.py)
  for RL train / evaluate / paper / replay / walk-forward.**
  Telemetry, `rl_runs` ledger, Iceberg trajectories, and
  hash-locked spec versions depend on it.
- **Don't mutate `rl_experiment_versions` rows.** They are
  immutable, hash-locked snapshots — re-snapshotting via
  [aqp/rl/registry.py::persist_spec](aqp/rl/registry.py) creates a
  new version row when the hash changes.
- **Don't write RL trajectories / equity / action / reward-decomp
  directly to Iceberg.** Buffer them through
  [`IcebergTrajectoryStore`](aqp/rl/trajectories/iceberg_writer.py)
  so `append_arrow` calls share batching, tenancy stamping, and
  flush semantics.
- **Don't decorate RL component subclasses manually with
  `@register`.** The
  [`RLComponent`](aqp/rl/core/base.py) metaclass does it for you when
  you set `rl_kind` + `rl_alias` (and optional `rl_tags` /
  `rl_source` / `rl_category`).
- **Don't call `litellm.completion` / `OllamaClient` from RL code.**
  `LLMHybridAgent` routes through
  [`router_complete`](aqp/llm/providers/router.py).

## Quick reference

| Concept | One-liner | File |
| --- | --- | --- |
| `Symbol.parse(vt_symbol)` | Canonical symbol parsing | [aqp/core/types.py](aqp/core/types.py) |
| `router_complete` | Single LLM call entry point | [aqp/llm/providers/router.py](aqp/llm/providers/router.py) |
| `iceberg_catalog.append_arrow` | Single Iceberg write entry point | [aqp/data/iceberg_catalog.py](aqp/data/iceberg_catalog.py) |
| `BaseBacktestEngine` + `EngineCapabilities` | Shared backtest engine ABC + capability dataclass | [aqp/backtest/base.py](aqp/backtest/base.py), [aqp/backtest/capabilities.py](aqp/backtest/capabilities.py) |
| `VectorbtProEngine` modes | Multi-mode dispatch (signals/orders/optimizer/holding/random) | [aqp/backtest/vbtpro/engine.py](aqp/backtest/vbtpro/engine.py) |
| `AgentDispatcher.consult` | Per-bar agent primitive exposed via `context['agents']` | [aqp/strategies/agentic/agent_dispatcher.py](aqp/strategies/agentic/agent_dispatcher.py) |
| `LedgerWriter` | Single ledger write entry point | [aqp/persistence/ledger.py](aqp/persistence/ledger.py) |
| `IngestionPipeline.run_path` | Generic file → Iceberg pipeline | [aqp/data/pipelines/runner.py](aqp/data/pipelines/runner.py) |
| `plan_ingestion` | Director planner (Nemotron) | [aqp/data/pipelines/director.py](aqp/data/pipelines/director.py) |
| `register("Name")` | Strategy / model factory decorator | [aqp/core/registry.py](aqp/core/registry.py) |
| `emit / emit_done / emit_error` | Task progress publish | [aqp/tasks/_progress.py](aqp/tasks/_progress.py) |
| `subscribe(task_id)` | Subscribe to task progress | [aqp/ws/broker.py](aqp/ws/broker.py) |
| `settings.<knob>` | Read any config | [aqp/config.py](aqp/config.py) |
| `HierarchicalRAG.query / walk` | Hierarchical RAG entry point | [aqp/rag/hierarchy.py](aqp/rag/hierarchy.py) |
| `AgentSpec` + `AgentRuntime` | Spec-driven agent contract + executor | [aqp/agents/spec.py](aqp/agents/spec.py), [aqp/agents/runtime.py](aqp/agents/runtime.py) |
| `RedisHybridMemory` | Working / episodic / reflection memory layer | [aqp/llm/memory.py](aqp/llm/memory.py) |
| `build_full_pipeline_graph` | Alpha-GPT three-stage agentic loop | [aqp/agents/graph/builder.py](aqp/agents/graph/builder.py) |
| `BotSpec` + `BotRuntime` | Bot blueprint + executor (backtest / paper / chat / deploy) | [aqp/bots/spec.py](aqp/bots/spec.py), [aqp/bots/runtime.py](aqp/bots/runtime.py) |
| `AlphaBacktestExperiment` | Train + register + deploy + backtest in one experiment, combined ML + trading metrics | [aqp/ml/alpha_backtest_experiment.py](aqp/ml/alpha_backtest_experiment.py), [aqp/ml/alpha_metrics.py](aqp/ml/alpha_metrics.py) |
| `aqp.ml.flows.run_flow` | Sync workbench flow dispatch (linear / decomposition / forecast / GARCH / ACF / ...) | [aqp/ml/flows.py](aqp/ml/flows.py) |
| `aqp.ml.adhoc.quick_*` | Notebook-friendly one-liners (ridge, ARIMA, iforest, FinBERT, ...) | [aqp/ml/adhoc/](aqp/ml/adhoc/) |
| `transform.ml_preprocessing` + `sink.ml_feature_snapshot` | ML preprocessing as data-engine nodes; feature-snapshot Iceberg sink | [aqp/data/fetchers/transforms/ml_preprocessing.py](aqp/data/fetchers/transforms/ml_preprocessing.py), [aqp/data/fetchers/sinks/ml_feature_snapshot_sink.py](aqp/data/fetchers/sinks/ml_feature_snapshot_sink.py) |
| `TradingBot` / `ResearchBot` | Bot subclasses (`build_bot(spec)` picks the right one) | [aqp/bots/trading_bot.py](aqp/bots/trading_bot.py), [aqp/bots/research_bot.py](aqp/bots/research_bot.py) |
| `DeploymentDispatcher` | Bot deploy target dispatch (paper / k8s / backtest_only) | [aqp/bots/deploy.py](aqp/bots/deploy.py) |
| `SinkRow` + `materialise_node_spec` | Project-scoped sink registry resolved into manifest `NodeSpec` | [aqp/persistence/models_sinks.py](aqp/persistence/models_sinks.py), [aqp/data/sinks/service.py](aqp/data/sinks/service.py) |
| `MarketDataProducerRow` + `ProducerSupervisor` | Producer registry + start/stop/scale lifecycle | [aqp/persistence/models_producers.py](aqp/persistence/models_producers.py), [aqp/streaming/producers/supervisor.py](aqp/streaming/producers/supervisor.py) |
| `StreamingDatasetLink` | Dataset ↔ topic / job / connector linkage graph | [aqp/persistence/models_streaming_links.py](aqp/persistence/models_streaming_links.py) |
| `NativeKafkaAdmin` / `FlinkRestClient` / `FlinkSessionJobK8s` | Native streaming admin facades | [aqp/streaming/admin/kafka_admin.py](aqp/streaming/admin/kafka_admin.py), [aqp/streaming/admin/flink_admin.py](aqp/streaming/admin/flink_admin.py) |
| `submit_factor_job` | Render + apply a Flink session-job for an AQP factor / ML pipeline | [aqp/streaming/runtime.py](aqp/streaming/runtime.py) |
| `ClusterMgmtClient` | Httpx wrapper around `rpi_kubernetes` `/api/{kafka,flink,alphavantage}` | [aqp/services/cluster_mgmt_client.py](aqp/services/cluster_mgmt_client.py) |
| `dataset_loading_assistant` | Read-only data-onboarding agent (Ollama via AgentRuntime) | [configs/agents/dataset_loading_assistant.yaml](configs/agents/dataset_loading_assistant.yaml) |
| `RLComponent` metaclass + `rl_kind` | Auto-registers concrete RL components by kind | [aqp/rl/core/base.py](aqp/rl/core/base.py) |
| `BaseRLEnv` | Composable env (observation / action / reward / termination hooks) | [aqp/rl/core/env.py](aqp/rl/core/env.py) |
| `CompositeReward` + `RewardTerm` | Sum of weighted reward terms with per-step decomposition | [aqp/rl/core/reward.py](aqp/rl/core/reward.py) |
| `BaseObservationBuilder` + `StackedObservationBuilder` | Compose feature blocks (FinRL stockstats / covariance / turbulence / VIX / lookback / fundamentals / microstructure) | [aqp/rl/core/observation.py](aqp/rl/core/observation.py) |
| `BaseActionSpace` (continuous / softmax / integer-shares / discrete / multi-discrete / target-position) | Declares gym space + transform | [aqp/rl/core/action.py](aqp/rl/core/action.py) |
| `BaseDataPipeline` (FinRL `DataProcessor` parity) | Iceberg / Yahoo / Alpaca / streaming / replay | [aqp/rl/core/data.py](aqp/rl/core/data.py), [aqp/rl/data_pipelines/](aqp/rl/data_pipelines/) |
| `RLExperimentSpec` + `RLRuntime` | Hash-locked spec + single sanctioned executor (mirrors `BotRuntime` / `AgentRuntime`) | [aqp/rl/spec.py](aqp/rl/spec.py), [aqp/rl/runtime.py](aqp/rl/runtime.py) |
| `IcebergTrajectoryStore` | Buffered Arrow writer for `rl.trajectories` / `rl.equity_curves` / `rl.action_logs` / `rl.reward_decomposition` | [aqp/rl/trajectories/iceberg_writer.py](aqp/rl/trajectories/iceberg_writer.py) |
| `WalkForwardEnsembler` | FinRL `DRLEnsembleAgent` port (rolling Sharpe-based pick) | [aqp/rl/ensemblers/walk_forward.py](aqp/rl/ensemblers/walk_forward.py) |
| `LLMHybridAgent` | FinRobot-style LLM advisor blended with RL backbone (LLM via `router_complete`) | [aqp/rl/agents/llm_hybrid.py](aqp/rl/agents/llm_hybrid.py) |
| `SB3Adapter` (PPO / SAC / TD3 / DDPG / DQN / sb3-contrib) | Stable-Baselines3 + sb3-contrib wrapper | [aqp/rl/agents/sb3_adapter.py](aqp/rl/agents/sb3_adapter.py) |
| `ElegantRLAdapter` / `RayRLlibAdapter` / `CleanRLAdapter` | FinRL parity backends (optional deps) | [aqp/rl/agents/elegantrl_adapter.py](aqp/rl/agents/elegantrl_adapter.py), [aqp/rl/agents/rllib_adapter.py](aqp/rl/agents/rllib_adapter.py), [aqp/rl/agents/cleanrl_adapter.py](aqp/rl/agents/cleanrl_adapter.py) |

## When in doubt

1. Read [docs/glossary.md](docs/glossary.md) for the term.
2. Read the relevant subsystem doc from [docs/index.md](docs/index.md).
3. Search the code: `rg "<symbol_or_name>" aqp/`.
4. If still stuck, file an issue or ask a maintainer; do **not**
   guess and ship.
