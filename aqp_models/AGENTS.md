# AGENTS.md

Agent contract for `aqp_models`.

## Purpose

This boundary owns custom model pulling, building, training, fine-tuning,
evaluating, and testing for the Agentic Quant Platform. It contains the
qlib-style ML framework, the Predictor Hub, the AlphaBacktestExperiment,
walk-forward training, the finetune trainers, every model implementation
(tree / linear / sklearn / forecast / anomaly / keras / tensorflow /
huggingface / SAE / SPM / torch zoo), and the custom model-serving
slice of `aqp/llm/` (vLLM and Ollama) — i.e. anything that pulls, builds,
trains, fine-tunes, evaluates, or tests a custom model.

The boundary also owns the matching Celery task wrappers
([`tasks/`](tasks/) — `ml_tasks.py`, `ml_test_tasks.py`,
`finetune_tasks.py`, `training_tasks.py`), the FastAPI routers
([`api/routes/`](api/routes/) — `ml.py`, `analytics_ml.py`), the YAML
spec library ([`configs/`](configs/)), and the test suite
([`tests/`](tests/)).

## Hard Boundaries

1. **All models register via `@register("Name", kind="model")`.** YAML
   loaders that resolve `class` / `module_path` / `kwargs` factory specs
   depend on this. Decorators are imported from
   [`aqp.core.registry`](../aqp/core/registry.py) (the central registry
   stays in the monolith).
2. **All ML model lifecycle (train / fit / predict / save / load) goes
   through the model class's `train`, `fit`, `predict`, `save`, `load`
   methods inherited from
   [`BaseModel`](src/aqp_models/base.py).** Tasks and routes wrap these
   methods; they never reach into a model's internals.
3. **All AlphaBacktestExperiment runs go through
   [`AlphaBacktestExperiment.run`](src/aqp_models/alpha_backtest_experiment.py).**
   Telemetry, the `ml_alpha_backtest_runs` ledger, and combined metrics
   depend on it.
4. **Workbench flows register via
   [`run_flow(...)` in `src/aqp_models/flows.py`](src/aqp_models/flows.py).**
   Add the new flow to `_FLOWS_BY_NAME` and `list_flows()` so the webui
   drawer picks it up.
5. **Custom model-serving lives in
   [`src/aqp_models/serving/`](src/aqp_models/serving/) — vLLM
   (`vllm.py`) and Ollama (`ollama.py`).** These are the model-pulling
   and self-hosted serving primitives. The central LLM gateway
   (`router_complete`) **stays in the monolith** at
   [`../aqp/llm/providers/router.py`](../aqp/llm/providers/router.py)
   and is the single LLM call entry point per the monolith Hard Rule 2.
6. **No raw ORM writes from this package.** Use `LedgerWriter` from the
   monolith for ledger rows. Test workbench tasks must respect Hard
   Rule 5 (cross-task state through Postgres only — pass IDs, re-fetch
   in the worker).
7. **All Iceberg writes go through
   [`iceberg_catalog.append_arrow`](../aqp/data/iceberg_catalog.py)**
   in the monolith with `medallion_layer` + `business_metadata` set.
   Don't call PyIceberg directly.

## Where Changes Go

- New ML model: implement in
  [`src/aqp_models/models/`](src/aqp_models/models/) following the
  `class` / `module_path` / `kwargs` pattern; decorate with
  `@register("Name", kind="model")`. Add a YAML example in
  [`configs/`](configs/).
- New workbench flow: implement `run_<flow>_flow(...)` in
  [`src/aqp_models/flows.py`](src/aqp_models/flows.py); register in
  `run_flow(...)` and `list_flows()`.
- New ML preprocessor pipeline node: subclass
  [`Processor`](src/aqp_models/processors.py).
- New finetune dataset / trainer: extend
  [`src/aqp_models/finetune/`](src/aqp_models/finetune/).
- New custom-serving adapter (e.g. TGI, llama.cpp): add a new module
  under [`src/aqp_models/serving/`](src/aqp_models/serving/).
- New Celery task: extend the appropriate file in
  [`tasks/`](tasks/) — `ml_tasks.py` (training), `ml_test_tasks.py`
  (test workbench), `finetune_tasks.py` (LLM finetune),
  `training_tasks.py` (job-flow training).
- New REST surface: extend
  [`api/routes/ml.py`](api/routes/ml.py) or
  [`api/routes/analytics_ml.py`](api/routes/analytics_ml.py).
- Tests: mirror the source path under [`tests/`](tests/).
- Persistence models for ML run ledgers stay in the monolith ORM at
  [`../aqp/persistence/`](../aqp/persistence/) — this package depends
  on those rows being there.

## Dependency rules

- This package depends on the monolith for: `iceberg_catalog.append_arrow`,
  `LedgerWriter`, `RequestContext`, ORM models, `_progress.emit`,
  `MetadataCache`, `MLflow` integration, the central registry
  (`aqp.core.registry.register`), and `router_complete` (only via the
  hosted LLM gateway — `aqp_models` never calls the gateway except
  through the explicit `LLMHybridAgent`-style adapter pattern).
- The reverse direction (`aqp.ml.*` -> `aqp_models.*` and
  `aqp.llm.{vllm_runner,ollama_client}` -> `aqp_models.serving.*`) is
  via deprecation shims in `../aqp/ml/__init__.py`,
  `../aqp/llm/vllm_runner.py`, and `../aqp/llm/ollama_client.py`.
- Optional ML framework dependencies (torch zoo, forecast, anomaly,
  keras, tensorflow, transformers, vLLM) live behind `pyproject.toml`
  extras; missing deps degrade gracefully with
  `contextlib.suppress(Exception)` in the package `__init__.py`.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```

## Migration note

The legacy import paths `aqp.ml.*` and `aqp.llm.{vllm_runner,ollama_client}`
are preserved through deprecation-warning shims in
[`../aqp/ml/__init__.py`](../aqp/ml/__init__.py),
[`../aqp/llm/vllm_runner.py`](../aqp/llm/vllm_runner.py), and
[`../aqp/llm/ollama_client.py`](../aqp/llm/ollama_client.py). Old call
sites keep working through one release cycle; new code should import
from `aqp_models.*` directly. See
[`../aqp_docs/repository-split.md`](../aqp_docs/repository-split.md) for
the full strangler-migration policy.
