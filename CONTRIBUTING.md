# Contributing to AQP

Welcome. This file is the **human onboarding guide** — pair with
[AGENTS.md](AGENTS.md) (the AI-agent rule-set) and
[docs/architecture.md](docs/architecture.md) (the system overview).

## Prerequisites

| Requirement | Why | How |
| --- | --- | --- |
| Python 3.11 | Type-checks and `match` statements | `pyenv install 3.11.x` or your distro's package |
| Docker Desktop | Default deployment uses docker-compose | Install from docker.com |
| **File sharing** for the warehouse drive | Iceberg lives at `C:/aqp-warehouse` | Settings → Resources → File sharing → add `/c/aqp-warehouse` (Windows) |
| Ollama (host) | Default LLM provider | `ollama serve` + `ollama pull nemotron-3-nano:30b` |
| Postgres client | Inspecting the ledger | `psql` or any GUI |
| Optional: NVIDIA GPU | Faster ML / LLM inference | – |
| Optional: Node 20+ | webui dev | `nvm install 20` |

## Bootstrap

### Quick path (Docker, all services)

```bash
# Clone + install editable so tests + scripts can import aqp
git clone <repo>
cd agentic_quant_platform
pip install -e ".[all]"
cp .env.example .env

# Create the host-persisted warehouse
mkdir -p /c/aqp-warehouse/iceberg /c/aqp-warehouse/staging /c/aqp-warehouse/logs

# Bring up the stack
docker compose up -d

# Apply migrations
docker exec aqp-api alembic upgrade head

# Smoke-test the catalog
docker exec aqp-api python -m scripts.iceberg_smoke
```

The webui is at <http://localhost:3000>; the API at <http://localhost:8000/docs>.

### Native path (no Docker)

```bash
pip install -e ".[all]"
cp .env.example .env

# Make sure Postgres + Redis + Chroma are reachable; set AQP_*_URL accordingly
alembic upgrade head
uvicorn aqp.api.main:app --reload &
celery -A aqp.tasks.celery_app worker --loglevel=info
```

The native path falls back to a local PyIceberg SQL catalog at
`./data/iceberg/`.

## How to do common things

Each walkthrough cites the canonical file and an existing example so
you can copy-paste, then specialise.

### Add an LLM provider

One-line registration. The router and tier resolution work
automatically.

1. Open [aqp/llm/providers/catalog.py](aqp/llm/providers/catalog.py).
2. Append a `ProviderSpec` to `PROVIDERS`:

   ```python
   "newprovider": ProviderSpec(
       slug="newprovider",
       litellm_prefix="newprovider/",
       env_key="NEWPROVIDER_API_KEY",
       settings_attr="newprovider_api_key",
       default_deep_model="np-best",
       default_quick_model="np-fast",
   ),
   ```

3. Add `newprovider_api_key: str = Field(default="")` to
   [aqp/config.py](aqp/config.py)'s `Settings` class.
4. Add `AQP_NEWPROVIDER_API_KEY=` to [.env.example](.env.example).
5. Use it: `router_complete(provider="newprovider", model="np-best", ...)`.

### Add an ML model

The factory pattern is `class` / `module_path` / `kwargs`.

1. Implement under [aqp/ml/models/](aqp/ml/models/) (e.g.
   `aqp/ml/models/my_model.py`):

   ```python
   class MyModel:
       def __init__(self, lookback: int = 30, **kwargs): ...
       def fit(self, X, y): ...
       def predict(self, X): ...
   ```

2. Add a YAML config under [configs/ml/](configs/ml/):

   ```yaml
   class: MyModel
   module_path: aqp.ml.models.my_model
   kwargs:
     lookback: 30
   ```

3. Reference the YAML from any feature-set / strategy that wants to
   train it.

### Add a data source

1. Implement an adapter in [aqp/providers/](aqp/providers/) (REST / DB
   / file). Reference example: [aqp/services/alpha_vantage_service.py](aqp/services/alpha_vantage_service.py).
2. Insert a row into `data_sources` (via UI or seed script) so the
   lineage tables can FK back to it.
3. If it produces OHLCV bars, wire it into the `provider_for_*`
   lookups in [aqp/data/](aqp/data/).
4. Document it in [docs/data-plane.md](docs/data-plane.md).

### Add an API route

1. Pick a route module under [aqp/api/routes/](aqp/api/routes/) (or
   add a new one if it's a new domain).
2. Define an `APIRouter()` and your endpoints.
3. Register the router in [aqp/api/main.py](aqp/api/main.py)
   (`app.include_router(...)`).
4. If the route kicks off long-running work, return `TaskAccepted`
   (see [aqp/api/schemas.py](aqp/api/schemas.py)) and wire to a
   Celery task.

Reference example:
[aqp/api/routes/data_pipelines.py](aqp/api/routes/data_pipelines.py).

### Add a Celery task

1. Open the right file under [aqp/tasks/](aqp/tasks/) (or add a new
   one).
2. Define the task:

   ```python
   from aqp.tasks._progress import emit, emit_done, emit_error
   from aqp.tasks.celery_app import celery_app

   @celery_app.task(bind=True, name="aqp.tasks.my_module.my_task")
   def my_task(self, *args, **kwargs):
       task_id = self.request.id or "local"
       emit(task_id, "start", "doing thing")
       try:
           result = ...
           emit_done(task_id, result)
           return result
       except Exception as exc:
           emit_error(task_id, str(exc))
           raise
   ```

3. If your file is new, add it to the `include` list in
   [aqp/tasks/celery_app.py](aqp/tasks/celery_app.py) and add a
   `task_routes` entry to send it to a queue.
4. Workers must be restarted to pick up new task modules.

### Add an ORM model

1. Add the class to the appropriate
   `aqp/persistence/models_*.py` (or `models.py` for cross-domain).
2. Generate a migration:

   ```bash
   docker exec aqp-api alembic revision --autogenerate -m "add foo"
   ```

3. Inspect the generated migration in
   [alembic/versions/](alembic/versions/) — autogenerate misses
   things like indexes and check constraints.
4. Apply it:

   ```bash
   docker exec aqp-api alembic upgrade head
   ```

5. Update [docs/data-dictionary.md](docs/data-dictionary.md) with
   the new table's columns.
6. Add the table to the relevant per-domain ERD in
   [docs/erd.md](docs/erd.md).

### Add a strategy

1. Subclass `IStrategy` (or use `FrameworkAlgorithm` and supply
   universe / alpha / portfolio / risk / execution models). See
   [aqp/strategies/framework.py](aqp/strategies/framework.py).
2. Decorate with `@register("MyStrategy")` from
   [aqp/core/registry.py](aqp/core/registry.py).
3. YAML config under [configs/strategies/](configs/strategies/).
4. Document in [docs/factor-research.md](docs/factor-research.md)
   if the strategy introduces a new pattern.

### Add a backtest engine

Backtest engines plug into the same `IStrategy` /
`IBrokerage` / `IDataQueueHandler` contracts. Subclass the base in
[aqp/backtest/engine.py](aqp/backtest/engine.py); see
[aqp/backtest/vectorbt_engine.py](aqp/backtest/vectorbt_engine.py)
for a reference implementation.

## Code style

- **Linting**: `ruff check aqp/` (config in `pyproject.toml`).
- **Formatting**: `ruff format aqp/`.
- **Imports**: stdlib → third-party → local, separated by blank
  lines. `from __future__ import annotations` at the top of every
  Python file.
- **Type hints**: required on public function signatures; private
  helpers can skip if obvious.
- **Docstrings**: triple-quoted, first line is a one-sentence summary.
  Document non-obvious invariants and side effects.
- **No emojis** in code or commit messages.
- **Logging**: `logger = logging.getLogger(__name__)` at module top;
  no `print` outside scripts/.

## Tests

```bash
# Whole suite
docker exec aqp-api python -m pytest

# Just the data pipeline
docker exec aqp-api python -m pytest tests/data/

# A single file with verbose output
docker exec aqp-api python -m pytest tests/data/test_director.py -v

# Match by name
docker exec aqp-api python -m pytest -k "director"
```

**Test conventions**:

- Mirror the source path: `aqp/data/pipelines/director.py` →
  `tests/data/test_director.py`.
- Use `monkeypatch` to stub LLM calls in any test that touches the
  `IngestionPipeline` (set `director_enabled=False` or patch
  `aqp.data.pipelines.director._call_llm`).
- Use the `iceberg_workspace` fixture from
  [tests/data/test_pipelines_smoke.py](tests/data/test_pipelines_smoke.py)
  to get a tmp PyIceberg catalog.
- Don't hit the network in tests. Don't depend on a real
  Postgres/Redis/Ollama.

## Commit + PR conventions

- **Commit messages**: focus on **why**, not **what**. One-sentence
  summary; blank line; body paragraphs explaining the rationale and
  any trade-offs. Reference issues/migration ids where relevant.
- **PR title**: imperative mood, ≤72 chars
  (`Add Director-driven regulatory ingest`).
- **PR description**: link to the issue, summary of changes, test plan
  (commands you ran).
- **No giant PRs**: split into atomic commits where possible. Doc
  changes can ride along with feature commits.
- **No force-pushing to `main`**.
- **Pre-merge checklist**:
  - [ ] tests pass locally
  - [ ] docs updated (data-dictionary, ERD, glossary as needed)
  - [ ] new env vars in `.env.example`
  - [ ] new dependencies in `pyproject.toml`
  - [ ] migration applied + reviewed (no autogenerate footguns)

## Where the docs live

```
docs/
├── index.md             ← TOC; start here
├── architecture.md      ← system component diagram (humans)
├── glossary.md          ← terms (used everywhere)
├── erd.md               ← entity-relationship diagrams
├── class-diagram.md     ← class hierarchies
├── data-dictionary.md   ← table-by-table reference
├── flows.md             ← end-to-end sequence diagrams
├── data-catalog.md      ← Iceberg + ingestion
├── data-plane.md        ← provider → DuckDB pipeline
├── domain-model.md      ← narrative on Symbol/types
├── core-types.md        ← Symbol / enums / dataclasses
├── factor-research.md   ← strategy authoring
├── backtest-engines.md  ← engine catalogue
├── strategy-lifecycle.md ← draft → backtest → paper → live
├── strategy-browser.md  ← UI flow
├── ml-framework.md      ← train → register → deploy
├── agentic-pipeline.md  ← crew architecture
├── providers.md         ← LLM provider registry
├── alpha-vantage.md     ← AV provider quirks
├── streaming.md         ← Kafka topics + ingesters
├── live-market.md       ← live subscribe + WS
├── paper-trading.md     ← session lifecycle
├── observability.md     ← OTEL + tracing
└── webui.md             ← Next.js page tree
AGENTS.md                ← AI agent rule-set (root)
CONTRIBUTING.md          ← this file (root)
```

## Help / questions

- **Architecture questions**: read [docs/architecture.md](docs/architecture.md).
- **Terminology**: [docs/glossary.md](docs/glossary.md).
- **Code search**: `rg "<thing>" aqp/`.
- **Stuck**: file an issue or ping a maintainer. Don't ship a guess.
