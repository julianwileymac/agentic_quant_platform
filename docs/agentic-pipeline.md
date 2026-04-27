# Agentic Pipeline — End-to-End Walkthrough

> Doc map: [docs/index.md](index.md) · See [docs/flows.md](flows.md#3-agentic-crew-run) for the canonical sequence diagram.

This guide walks through the AQP agentic-trading lifecycle: download an
LLM, serve it, register a data source, queue a backtest, and let the
crew analyse the results. Each step is exercised from the Next.js
webui, but every action also has a REST + CLI surface so you can script
the same flow.

```mermaid
flowchart LR
    subgraph LLM["1. Models & Providers"]
        Pull[Ollama pull]
        Vllm[vLLM compose up]
        Defaults[Provider defaults]
    end
    subgraph DATA["2. Data sources"]
        Settings[Settings → Data sources]
        Inspect[Parquet inspector]
        Iceberg[Iceberg Editor]
        Consolidate[Consolidate part-tables]
    end
    subgraph WIZARD["3. Backtest wizard"]
        Picker[Dataset picker]
        MLPreview[ML alpha preview]
        Submit[POST /agentic/pipeline]
    end
    subgraph REVIEW["4. Review"]
        Stream[/chat/stream/{task_id}]
        Judge[LLM-as-judge]
        Detail[Backtest detail]
    end
    LLM --> WIZARD
    DATA --> WIZARD
    WIZARD --> REVIEW
```

## 1 — Pick or pull an LLM

Open `/models` (System → **Models & Providers**).

- **Ollama** — type a model tag in *Pull a model* (e.g. `nemotron`,
  `llama3.2`, `qwen2:7b`) and click **Pull**. A Celery task streams
  progress over `/chat/stream/{task_id}` so the page shows a real-time
  download bar. Existing local models are listed alongside; click
  *Delete* to free disk space.

- **vLLM** — every YAML under `configs/llm/*.yaml` becomes a profile
  card showing compose status, served models, and `Start` / `Stop`
  buttons. The page maps the profile to its docker-compose service
  (`vllm` for Nemotron, `vllm-fingpt` for the FinGPT LoRA preset).
  Starting a profile auto-saves its `base_url` as the active vLLM
  endpoint.

- **Provider defaults** — the bottom card persists the deep / quick
  model and Ollama / vLLM endpoints used by every agentic backtest.

REST equivalents (each returns `TaskAccepted` for streaming endpoints):

```bash
curl -X POST localhost:8000/agentic/models/pull -d '{"name":"llama3.2"}' -H 'content-type: application/json'
curl -X DELETE localhost:8000/agentic/models/llama3.2
curl -X GET    localhost:8000/agentic/models/running
curl -X GET    localhost:8000/agentic/vllm/profiles
curl -X POST   localhost:8000/agentic/vllm/start -d '{"profile":"vllm_nemotron"}' -H 'content-type: application/json'
```

## 2 — Register a data source

### Local partitioned parquet

Open `/settings` and scroll to **Backtest data sources**:

1. Pick **Parquet root** as the kind, fill in **Name** and a path.
2. Click **Inspect path** — the API walks the directory and returns
   file count, total bytes, partition keys (Hive-style
   `year=2024/month=01/...`), the column list, and a heuristic column
   map (`vt_symbol → ticker`, `timestamp → date`, etc.).
3. Toggle **Hive partitioning** if the inspector found
   `key=value` segments, and adjust the **Glob pattern** + **Column
   map** if the auto-suggestions need tuning.
4. **Save source**. The runtime control plane stores the config; the
   backtest runner forwards it through `DuckDBHistoryProvider`.

REST: `POST /backtest/data-sources/inspect` then
`POST /backtest/data-sources`.

### Iceberg tables

Browse the `/data/catalog` page or jump to the new `/data/iceberg`
**Iceberg Editor**:

- Inline edit description / domain / tags via `PATCH /datasets/{ns}/{name}`.
- Drop a stale table.
- **Multi-select rows → Consolidate**: opens the consolidation drawer
  (described below) so you can merge mis-loaded parts back together.

### Physical consolidation

Some upstream loaders write a single logical dataset as
`foo_part_1` … `foo_part_n`. To merge them:

1. Navigate to `/data/iceberg/consolidate` (Iceberg Editor → *Auto-suggest groups*).
2. Pick a strategy: **heuristic** (regex over names) or **llm-driven**
   (asks the configured router to suggest groupings; falls back to
   heuristic on failure).
3. Click **Propose groups** — review side-by-side suggestions.
4. Hit **Consolidate** on a group. The drawer:
   - Pre-fills a target identifier (longest-common-prefix heuristic).
   - Defaults to **dry-run** so you can inspect the row counts and
     schema-conflict report without writing.
   - When you uncheck **Dry run**, you must also tick *I understand
     this will drop the original tables* before the API accepts the
     non-dry-run request. The server enforces this with a 400 if
     `confirm` is missing.

The Celery task streams progress (`emit(stage, percent, message)`) so
the drawer shows a live consolidation log.

REST: `POST /datasets/grouping/{propose,consolidate}`.

## 3 — Queue an agentic backtest

Open `/backtest/new` (Lab → **Backtests** → *New*) and stay on the
**Agent backtest wizard** tab. The wizard's metadata step now
includes:

- **Agentic runtime** — provider, deep / quick model, debate rounds,
  `x_backtests`, rebalance frequency, mode, universe filters
  (`max_symbols`, `rotate_symbols`, `fixed`/`rolling` window), entry /
  exit conditions.
- **Data source** — embedded `DatasetCatalogPicker` with three tabs
  (configured sources / Iceberg catalog / ad-hoc) and a *Preview
  availability* button that hits `GET /datasets/{ns}/{name}/preview-bars`.
- **ML alpha** — toggle to swap the rule-based alpha with a
  `DeployedModelAlpha`, optionally **ensemble** with the rule-based
  alpha (uses `EnsembleAlpha`). When a deployment is selected, the
  *Preview ML alpha* card calls `POST /ml/deployments/{id}/preview` and
  shows last-N predictions on the chosen universe + window.

Submit fires `POST /agentic/pipeline`, returns a `task_id`, and the
right-hand panel streams `/chat/stream/{task_id}`.

## 4 — Review

- **Backtest detail** (`/backtest/{id}`) — equity curve, KPI strip,
  judge report, replay drawer.
- **LLM-as-judge** — runs automatically when *Run an LLM-as-judge after
  the backtest completes* is ticked in the wizard's Judge step.
- **Crew Trace** (`/crew`) — live swim-lane view of the agent
  interactions for the active run.

## Inspiration extracts

These reusable building blocks were ported (non-demo only) from
the inspiration codebases:

- `aqp.strategies.universes.QuarterlyRotationUniverse` — daily universe
  driven by quarterly stock-selection rows + a trading calendar
  (FinRL-X's `UniverseManager`).
- `aqp.strategies.regime_detection.slow_regime` /
  `fast_overlay` — three-state risk gate using SPX trend + 13-week
  drawdown + VIX z-score (FinRL-X's `market_regime`).
- `aqp.agents.tools.backtrader_tool.BacktraderTool` — agent-callable
  single-ticker Backtrader backtest (FinRobot's `BackTraderUtils`).
- `aqp.agents.prompts.forecaster.build_forecaster_prompt` — FinGPT
  Forecaster's weekly prompt template, decoupled from the original's
  Finnhub / OpenAI glue so it composes with `router_complete`.
- `aqp.utils.keys.register_keys_from_json` — bulk env-var injection
  from a credentials JSON file (FinRobot's `register_keys_from_json`).
