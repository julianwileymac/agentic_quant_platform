# aqp_rl

Status: active boundary package. Reinforcement-learning subsystem for the
Agentic Quant Platform.

`aqp_rl` owns the hash-locked `RLExperimentSpec` + `RLRuntime` contract,
the `RLComponent` metaclass that auto-registers every concrete RL
component, all advantage estimators, policy backbones, the weight-centric
portfolio pipeline, the Iceberg-backed trajectory store, and the matching
Celery task + FastAPI route + YAML spec library.

## Owns

- Spec runtime contract: `src/aqp_rl/spec.py`, `src/aqp_rl/runtime.py`,
  `src/aqp_rl/registry.py`.
- Core abstractions: `src/aqp_rl/core/` — env, observation, action, reward,
  termination, policy, agent, data pipeline, ensembler, experiment,
  trajectory store; plus the `RLComponent` metaclass.
- Component libraries: `src/aqp_rl/envs/`, `src/aqp_rl/rewards/`,
  `src/aqp_rl/observations/`, `src/aqp_rl/actions/`,
  `src/aqp_rl/terminations/`, `src/aqp_rl/policies/`,
  `src/aqp_rl/data_pipelines/`, `src/aqp_rl/agents/`,
  `src/aqp_rl/ensemblers/`, `src/aqp_rl/experiments/`,
  `src/aqp_rl/applications/`, `src/aqp_rl/portfolio/`,
  `src/aqp_rl/bridges/`, `src/aqp_rl/advantage/`,
  `src/aqp_rl/trajectories/`, `src/aqp_rl/execution/`.
- Celery task wrapper: `tasks/rl_tasks.py`.
- FastAPI router: `api/routes/rl.py`.
- YAML spec library: `configs/`.
- Test suite: `tests/`.

## Layout

```text
aqp_rl/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── INDEX.md
├── src/
│   └── aqp_rl/
│       ├── __init__.py
│       ├── spec.py
│       ├── runtime.py
│       ├── registry.py
│       ├── trainer.py
│       ├── evaluator.py
│       ├── tagging.py
│       ├── core/
│       ├── envs/
│       ├── rewards/
│       ├── observations/
│       ├── actions/
│       ├── terminations/
│       ├── policies/
│       ├── data_pipelines/
│       ├── agents/
│       ├── ensemblers/
│       ├── experiments/
│       ├── applications/
│       ├── portfolio/
│       ├── bridges/
│       ├── advantage/
│       ├── trajectories/
│       └── execution/
├── tasks/
│   └── rl_tasks.py
├── api/
│   └── routes/
│       └── rl.py
├── configs/
│   ├── ppo_portfolio.yaml
│   ├── sac_trading.yaml
│   ├── presets/
│   ├── rewards/
│   ├── observations/
│   ├── policies/
│   ├── data_pipelines/
│   └── spm/
└── tests/
    ├── test_runtime.py
    ├── test_routes_rl.py
    ├── envs/
    ├── advantage/
    ├── policies/
    └── portfolio/
```

## Current Source Locations

| Responsibility | Current path |
| --- | --- |
| Runtime package | `src/aqp_rl/` |
| Celery task | `tasks/rl_tasks.py` |
| FastAPI route | `api/routes/rl.py` |
| Persistence models | `../aqp/persistence/models_rl.py` (monolith — stays) |
| Spec library | `configs/` |
| Tests | `tests/` |
| Canonical doc | `../aqp_docs/rl-framework.md` |

## Dependencies

This package depends on the monolith for:

- `iceberg_catalog.append_arrow` (Hard Rule 3) for trajectory writes.
- `router_complete` (Hard Rule 2) for `LLMHybridAgent` LLM calls.
- `LedgerWriter`, `RequestContext`, ORM models, `_progress.emit`,
  `MetadataCache`, `RiskLimits`, `TargetWeightsRebalancer`.

The reverse direction (`aqp.rl.*` -> `aqp_rl.*`) is preserved through
deprecation-warning shims in `../aqp/rl/__init__.py`.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```

## Migration note

Legacy import path `aqp.rl.*` is preserved through deprecation-warning
shims in [`../aqp/rl/__init__.py`](../aqp/rl/__init__.py). Old call sites
keep working through one release cycle; new code should import from
`aqp_rl.*` directly. Strangler-migration policy is documented in
[`../aqp_docs/repository-split.md`](../aqp_docs/repository-split.md).

## Canonical doc

[../aqp_docs/rl-framework.md](../aqp_docs/rl-framework.md) plus the
existing companion docs:

- `../aqp_docs/rl-lab.md`
- `../aqp_docs/rl-components.md`
- `../aqp_docs/rl-iceberg.md`
- `../aqp_docs/rl-policy-backbones.md`
- `../aqp_docs/weight-centric-pipeline.md`
