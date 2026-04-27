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
| [aqp/agents/](aqp/agents/) | CrewAI agents, prompts, tools | [docs/agentic-pipeline.md](docs/agentic-pipeline.md) |
| [aqp/api/](aqp/api/) | FastAPI app + 30 route modules under `routes/` | [docs/architecture.md](docs/architecture.md) |
| [aqp/backtest/](aqp/backtest/) | Backtest engines (`bt`, `vectorbt`, custom) + result handlers | [docs/backtest-engines.md](docs/backtest-engines.md) |
| [aqp/cli/](aqp/cli/) | `aqp` CLI commands | – |
| [aqp/core/](aqp/core/) | `Symbol`, enums, dataclasses, interfaces | [docs/core-types.md](docs/core-types.md) |
| [aqp/data/](aqp/data/) | Iceberg catalog wrapper, generic ingestion pipeline, indicator zoo | [docs/data-catalog.md](docs/data-catalog.md), [docs/data-plane.md](docs/data-plane.md) |
| [aqp/llm/](aqp/llm/) | Provider registry, LiteLLM router, Ollama client | [docs/providers.md](docs/providers.md) |
| [aqp/ml/](aqp/ml/) | ML model factory, feature engineering, deployments | [docs/ml-framework.md](docs/ml-framework.md) |
| [aqp/mlops/](aqp/mlops/) | MLflow autolog hooks, lineage helpers | [docs/observability.md](docs/observability.md) |
| [aqp/observability/](aqp/observability/) | OTEL setup, tracers | [docs/observability.md](docs/observability.md) |
| [aqp/persistence/](aqp/persistence/) | SQLAlchemy ORM (11 model files) + `LedgerWriter` | [docs/erd.md](docs/erd.md), [docs/data-dictionary.md](docs/data-dictionary.md) |
| [aqp/providers/](aqp/providers/) | Data-feed adapters (yfinance, AV, IBKR, …) | [docs/data-plane.md](docs/data-plane.md) |
| [aqp/risk/](aqp/risk/) | Position-, daily-, drawdown-loss limits | [docs/paper-trading.md](docs/paper-trading.md) |
| [aqp/rl/](aqp/rl/) | gym envs + thin SB3 adapters | [docs/ml-framework.md](docs/ml-framework.md) |
| [aqp/runtime/](aqp/runtime/) | Control-plane state (provider overrides, kill switches) | [docs/providers.md](docs/providers.md) |
| [aqp/services/](aqp/services/) | Higher-level domain services (Alpha Vantage, Tradier, …) | [docs/alpha-vantage.md](docs/alpha-vantage.md) |
| [aqp/strategies/](aqp/strategies/) | `BaseStrategy` + concrete alphas + framework | [docs/factor-research.md](docs/factor-research.md) |
| [aqp/streaming/](aqp/streaming/) | Kafka producers/consumers, IBKR + Alpaca ingesters | [docs/streaming.md](docs/streaming.md) |
| [aqp/tasks/](aqp/tasks/) | Celery tasks (backtest / ingest / agents / paper / ml / etc) | (per consumer doc) |
| [aqp/trading/](aqp/trading/) | Paper trading session loop, broker abstractions | [docs/paper-trading.md](docs/paper-trading.md) |
| [aqp/ui/](aqp/ui/) | **Legacy Solara UI** — under `legacy` profile only | – |
| [aqp/utils/](aqp/utils/) | Cross-cutting helpers (key derivation, etc) | – |
| [aqp/ws/](aqp/ws/) | Redis pub/sub bridge + WebSocket helpers | – |

External code:

| Path | Purpose |
| --- | --- |
| [webui/](webui/) | Next.js 15 React webui |
| [alembic/versions/](alembic/versions/) | DB migrations (immutable once shipped) |
| [deploy/k8s/](deploy/k8s/) | Kubernetes manifests for the rpi_kubernetes cluster |
| [scripts/](scripts/) | Operational scripts (`iceberg_smoke.py`, `ingest_regulatory.py`, …) |
| [configs/](configs/) | YAML configs (strategies, agents, ML models, LLM profiles) |
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
| Add an ML model | Implement in [aqp/ml/models/](aqp/ml/models/) following the `class`/`module_path`/`kwargs` pattern; add a YAML example in [configs/ml/](configs/ml/) |
| Add a data source | Implement adapter in [aqp/providers/](aqp/providers/) or [aqp/services/](aqp/services/); register in [aqp/persistence/models.py::DataSource](aqp/persistence/models.py); document in [docs/data-plane.md](docs/data-plane.md) |
| Add a persistence model | Add the class to the right `aqp/persistence/models_*.py` file; create an Alembic migration; update [docs/data-dictionary.md](docs/data-dictionary.md) and the relevant ERD section in [docs/erd.md](docs/erd.md) |
| Add a strategy | Subclass `IStrategy` (or use `FrameworkAlgorithm`) in [aqp/strategies/](aqp/strategies/); decorate with `@register("Name")`; YAML config under [configs/strategies/](configs/strategies/) |
| Add a backtest engine | Subclass the base in [aqp/backtest/engine.py](aqp/backtest/engine.py); register if invoked by name from YAML |
| Add a feature / indicator | [aqp/data/indicators_zoo.py](aqp/data/indicators_zoo.py) — append to the spec map |
| Add a test | Mirror the source path under [tests/](tests/); use the existing fixtures |
| Inspect Iceberg catalog | `from pyiceberg.catalog import load_catalog; load_catalog("aqp", type="sql", uri="sqlite:///C:/aqp-warehouse/iceberg/catalog.db", warehouse="file:///C:/aqp-warehouse/iceberg")` |
| Find every place a task is dispatched | `rg "<task_module>\.<task_name>\.delay\(" aqp/` |
| Find every config knob | [aqp/config.py](aqp/config.py) (single source of truth) |

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

## Quick reference

| Concept | One-liner | File |
| --- | --- | --- |
| `Symbol.parse(vt_symbol)` | Canonical symbol parsing | [aqp/core/types.py](aqp/core/types.py) |
| `router_complete` | Single LLM call entry point | [aqp/llm/providers/router.py](aqp/llm/providers/router.py) |
| `iceberg_catalog.append_arrow` | Single Iceberg write entry point | [aqp/data/iceberg_catalog.py](aqp/data/iceberg_catalog.py) |
| `LedgerWriter` | Single ledger write entry point | [aqp/persistence/ledger.py](aqp/persistence/ledger.py) |
| `IngestionPipeline.run_path` | Generic file → Iceberg pipeline | [aqp/data/pipelines/runner.py](aqp/data/pipelines/runner.py) |
| `plan_ingestion` | Director planner (Nemotron) | [aqp/data/pipelines/director.py](aqp/data/pipelines/director.py) |
| `register("Name")` | Strategy / model factory decorator | [aqp/core/registry.py](aqp/core/registry.py) |
| `emit / emit_done / emit_error` | Task progress publish | [aqp/tasks/_progress.py](aqp/tasks/_progress.py) |
| `subscribe(task_id)` | Subscribe to task progress | [aqp/ws/broker.py](aqp/ws/broker.py) |
| `settings.<knob>` | Read any config | [aqp/config.py](aqp/config.py) |

## When in doubt

1. Read [docs/glossary.md](docs/glossary.md) for the term.
2. Read the relevant subsystem doc from [docs/index.md](docs/index.md).
3. Search the code: `rg "<symbol_or_name>" aqp/`.
4. If still stuck, file an issue or ask a maintainer; do **not**
   guess and ship.
