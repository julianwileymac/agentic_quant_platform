# aqp_models

Status: active boundary package. Custom model pulling, building, training,
fine-tuning, evaluating, and testing for the Agentic Quant Platform.

`aqp_models` owns the qlib-style ML framework, the Predictor Hub, the
AlphaBacktestExperiment, walk-forward training, every model
implementation (tree / linear / sklearn / forecast / anomaly / keras /
tensorflow / huggingface / SAE / SPM / torch zoo), the finetune
trainers, the workbench flows, and the custom model-serving slice of
`aqp/llm/` (vLLM and Ollama). The central LLM gateway
(`router_complete`) stays in the monolith.

## Owns

- ML framework abstractions: `src/aqp_models/{base,dataset,handler,loader,planning,processors,recorder,splits,sampling,importance,bet_sizing}.py`.
- Model implementations: `src/aqp_models/models/{tree,linear,sklearn,forecasting,anomaly,keras,tensorflow,huggingface,ensemble,naive_bayes,highfreq_gbdt,sae,spm,torch,notebooks}/`.
- Feature factories: `src/aqp_models/features/{alpha158,alpha360}.py`.
- Workbench: `src/aqp_models/{flows,pipeline_recipes,walk_forward,experiments,alpha_backtest_experiment,alpha_metrics,factor_eval}.py`.
- Predictor Hub: `src/aqp_models/predictors/`.
- Adhoc helpers (notebooks): `src/aqp_models/adhoc/`.
- Labeling: `src/aqp_models/labeling/`.
- Applications (forecaster, sentiment): `src/aqp_models/applications/`.
- Finetune trainers: `src/aqp_models/finetune/`.
- Custom model serving (model pulling + in-process / self-hosted serving):
  `src/aqp_models/serving/{vllm,ollama}.py`.
- Celery task wrappers: `tasks/ml_tasks.py`, `tasks/ml_test_tasks.py`,
  `tasks/finetune_tasks.py`, `tasks/training_tasks.py`.
- FastAPI routers: `api/routes/ml.py`, `api/routes/analytics_ml.py`.
- YAML spec library: `configs/`.
- Test suite: `tests/`.

## Layout

```text
aqp_models/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── INDEX.md
├── src/
│   └── aqp_models/
│       ├── __init__.py
│       ├── base.py
│       ├── dataset.py
│       ├── handler.py
│       ├── loader.py
│       ├── planning.py
│       ├── processors.py
│       ├── recorder.py
│       ├── splits.py
│       ├── sampling.py
│       ├── importance.py
│       ├── bet_sizing.py
│       ├── flows.py
│       ├── pipeline_recipes.py
│       ├── walk_forward.py
│       ├── experiments.py
│       ├── alpha_backtest_experiment.py
│       ├── alpha_metrics.py
│       ├── factor_eval.py
│       ├── features/
│       ├── models/
│       ├── predictors/
│       ├── adhoc/
│       ├── labeling/
│       ├── applications/
│       ├── finetune/
│       └── serving/
│           ├── vllm.py
│           └── ollama.py
├── tasks/
│   ├── ml_tasks.py
│   ├── ml_test_tasks.py
│   ├── finetune_tasks.py
│   └── training_tasks.py
├── api/
│   └── routes/
│       ├── ml.py
│       └── analytics_ml.py
├── configs/
│   ├── alpha158_lstm.yaml
│   ├── attention_all.yaml
│   ├── alpha_backtest/
│   ├── frameworks/
│   ├── ml4t/
│   ├── qlib/
│   ├── notebooks/
│   ├── tutorials/
│   ├── sae/
│   ├── spm/
│   ├── finrl_trading/
│   └── ...
└── tests/
    ├── models/
    └── predictors/
```

## Current Source Locations

| Responsibility | Current path |
| --- | --- |
| ML framework | `src/aqp_models/` |
| Custom model serving | `src/aqp_models/serving/` |
| Celery tasks | `tasks/` |
| FastAPI routes | `api/routes/` |
| Persistence models | `../aqp/persistence/models_ml.py`, `../aqp/persistence/models_alpha_backtest.py` (monolith — stays) |
| Spec library | `configs/` |
| Tests | `tests/` |
| Canonical doc | `../aqp_docs/ml-framework.md` |

## Dependencies

This package depends on the monolith for:

- `iceberg_catalog.append_arrow` for Iceberg writes.
- `LedgerWriter`, `RequestContext`, ORM models, `_progress.emit`,
  `MetadataCache`.
- The central registry (`aqp.core.registry.register`).
- `router_complete` (only used through the explicit `LLMHybridAgent`-style
  adapter pattern; never the default LLM call path).

The reverse direction (`aqp.ml.*` -> `aqp_models.*`,
`aqp.llm.{vllm_runner,ollama_client}` -> `aqp_models.serving.*`) is
preserved through deprecation-warning shims in
`../aqp/ml/__init__.py`, `../aqp/llm/vllm_runner.py`, and
`../aqp/llm/ollama_client.py`.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```

## Migration note

Legacy import paths `aqp.ml.*` and `aqp.llm.{vllm_runner,ollama_client}`
are preserved through deprecation-warning shims. Old call sites keep
working through one release cycle; new code should import from
`aqp_models.*` directly. Strangler-migration policy is documented in
[`../aqp_docs/repository-split.md`](../aqp_docs/repository-split.md).

## Canonical doc

[../aqp_docs/ml-framework.md](../aqp_docs/ml-framework.md) plus the
existing companion docs:

- `../aqp_docs/ml-libraries.md`
- `../aqp_docs/ml-flows.md`
- `../aqp_docs/ml-alpha-backtest.md`
- `../aqp_docs/predictor-hub.md`
