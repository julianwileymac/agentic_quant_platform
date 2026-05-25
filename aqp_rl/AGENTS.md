# AGENTS.md

Agent contract for `aqp_rl`.

## Purpose

This boundary owns the AQP reinforcement-learning subsystem: hash-locked
[`RLExperimentSpec`](src/aqp_rl/spec.py) blueprints, the single sanctioned
[`RLRuntime`](src/aqp_rl/runtime.py) executor, the
[`RLComponent`](src/aqp_rl/core/base.py) metaclass that auto-registers every
concrete env / observation / action / reward / termination / policy / agent /
data pipeline / ensembler / experiment / trajectory store, all advantage
estimators ([`src/aqp_rl/advantage/`](src/aqp_rl/advantage/)), policy
backbones ([`src/aqp_rl/policies/`](src/aqp_rl/policies/)), the
weight-centric four-stage portfolio pipeline
([`src/aqp_rl/portfolio/`](src/aqp_rl/portfolio/)), and the Iceberg-backed
trajectory store ([`src/aqp_rl/trajectories/`](src/aqp_rl/trajectories/)).

The boundary also owns the matching Celery task wrapper
([`tasks/rl_tasks.py`](tasks/rl_tasks.py)), the FastAPI router
([`api/routes/rl.py`](api/routes/rl.py)), the YAML spec library
([`configs/`](configs/)), and the test suite ([`tests/`](tests/)).

## Hard Boundaries

1. **All RL train / evaluate / paper / replay / walk-forward go through
   `RLRuntime`.** Telemetry, the `rl_runs` ledger, Iceberg trajectories,
   and hash-locked `rl_experiment_versions` snapshots all depend on it.
   Celery tasks and API routes wrap it — they never call `agent.train`
   directly.
2. **`rl_experiment_versions` rows are immutable, hash-locked snapshots.**
   Re-snapshotting via
   [`registry.persist_spec`](src/aqp_rl/registry.py) inserts a new
   version row when the SHA-256 hash changes.
3. **Every concrete RL component registers via the
   [`RLComponent`](src/aqp_rl/core/base.py) metaclass.** Set ``rl_kind``
   to one of the canonical kinds (`rl_env`, `rl_reward`,
   `rl_observation`, `rl_action`, `rl_termination`, `rl_policy`,
   `rl_agent`, `rl_data`, `rl_ensembler`, `rl_experiment`,
   `rl_advantage_estimator`, `rl_policy_backbone`, `rl_trajectory_store`)
   and `rl_alias`. Don't decorate with `@register` manually.
4. **All trajectory / equity-curve / action-log / reward-decomposition
   writes go through
   [`IcebergTrajectoryStore`](src/aqp_rl/trajectories/iceberg_writer.py)**
   → `iceberg_catalog.append_arrow`. Never call PyIceberg directly from
   RL code.
5. **LLM calls inside `LLMHybridAgent` and any other RL component route
   through `router_complete`** (in the monolith at
   [`aqp/llm/providers/router.py`](../aqp/llm/providers/router.py)). No
   direct `litellm.completion` / `OllamaClient` from RL code.
6. **All weight-centric portfolio actions go through the four-stage
   pipeline** `f_S -> f_A -> f_T -> f_R` in
   [`src/aqp_rl/portfolio/pipeline.py`](src/aqp_rl/portfolio/pipeline.py).
   The risk overlay (`f_R`) re-uses
   [`RiskLimits`](../aqp/risk/limits.py) and
   [`TargetWeightsRebalancer`](../aqp/strategies/portfolio_construction.py)
   so offline backtest and live paper-trading produce identical
   target-weight vectors. Don't bypass the pipeline by writing weights
   directly into broker calls.
7. **All advantage estimation goes through
   [`BaseAdvantageEstimator`](src/aqp_rl/advantage/base.py)** subclasses
   (`rl_kind="rl_advantage_estimator"`). Native estimators
   (REINFORCE++, GRPO, GAE) ship in this package; NeMo-RL is a heavy
   optional adapter.
8. **All RL policy backbones go through
   [`TimeSeriesEncoder`](src/aqp_rl/policies/backbones/base.py)**
   subclasses (`rl_kind="rl_policy_backbone"`). The four shipped
   backbones (Transformer, Recurrent, Autoencoder, PatchTST) wrap
   existing `aqp.ml.models` modules so the policy network and the
   offline ML stack share one source of truth.

## Where Changes Go

- New env / reward / observation / action / termination / policy / agent /
  data / ensembler / experiment / trajectory_store: subclass the matching
  base in [`src/aqp_rl/core/`](src/aqp_rl/core/) and set `rl_kind` +
  `rl_alias`. The metaclass auto-registers; do not decorate manually.
- New advantage estimator: subclass
  [`BaseAdvantageEstimator`](src/aqp_rl/advantage/base.py) and set
  `rl_kind="rl_advantage_estimator"`.
- New policy backbone: subclass
  [`TimeSeriesEncoder`](src/aqp_rl/policies/backbones/base.py) and set
  `rl_kind="rl_policy_backbone"`.
- New Celery task: extend [`tasks/rl_tasks.py`](tasks/rl_tasks.py).
- New REST surface: extend [`api/routes/rl.py`](api/routes/rl.py).
- New YAML spec template: drop in [`configs/`](configs/) (or one of its
  subdirectories: `presets/`, `rewards/`, `observations/`, `policies/`,
  `data_pipelines/`, `spm/`).
- Tests: mirror the source path under [`tests/`](tests/).
- Persistence models for `rl_runs` + `rl_experiment_versions` stay in
  the monolith ORM at [`../aqp/persistence/`](../aqp/persistence/) — this
  package depends on those rows being there.

## Dependency rules

- This package depends on the monolith for: `iceberg_catalog.append_arrow`
  (Hard Rule 3 in the root `AGENTS.md`), `router_complete` (Hard Rule 2),
  `LedgerWriter`, `RequestContext`, ORM models, `_progress.emit`,
  `MetadataCache`, `RiskLimits`, `TargetWeightsRebalancer`. The reverse
  direction (`aqp.rl.*` -> `aqp_rl.*`) is via deprecation shims in
  `../aqp/rl/__init__.py`.
- Optional framework adapters (ElegantRL, RLlib, CleanRL, NeMo-RL,
  mbt-gym, FinRL) live behind `pyproject.toml` extras; missing deps
  degrade gracefully with `contextlib.suppress(Exception)` in the
  package `__init__.py`.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```

## Migration note

The legacy import path `aqp.rl.*` is preserved through deprecation-warning
shims in [`../aqp/rl/__init__.py`](../aqp/rl/__init__.py). Old call sites
keep working through one release cycle; new code should import from
`aqp_rl.*` directly. See [`../aqp_docs/docs/concepts/platform/repository-split.md`](../aqp_docs/docs/concepts/platform/repository-split.md)
for the full strangler-migration policy.
