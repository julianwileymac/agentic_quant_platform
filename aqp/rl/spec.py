"""Declarative ``RLExperimentSpec`` — reproducible RL blueprint.

Mirrors :class:`aqp.bots.spec.BotSpec` and
:class:`aqp.agents.spec.AgentSpec`. A spec is hash-locked: identical
specs collapse to one ``rl_experiment_versions`` row, and any historical
run can always be replayed against the exact spec it was built from.

Spec composition
----------------

```yaml
name: ppo-portfolio-finrl
slug: ppo-portfolio-finrl
kind: training
description: PPO over FinRL StockPortfolioEnv with Sharpe + drawdown reward.

universe:
  symbols: [AAPL.NASDAQ, MSFT.NASDAQ, GOOGL.NASDAQ]

data_pipeline:
  class: IcebergRLDataPipeline
  module_path: aqp.rl.data_pipelines.iceberg
  kwargs:
    indicators: [macd, rsi_30, sma_20, sma_50, turbulence]
    use_vix: false
    use_turbulence: true

env:
  class: StockTradingEnv
  module_path: aqp.rl.envs.stock_trading_env
  kwargs:
    start: "2018-01-01"
    end: "2023-06-30"
    initial_balance: 100000.0
    transaction_cost_pct: 0.001

reward:
  class: CompositeReward
  module_path: aqp.rl.core.reward
  kwargs:
    terms:
      - { class: PnLTerm, kwargs: { weight: 1.0 } }
      - { class: TurnoverPenaltyTerm, kwargs: { weight: 0.5, cost_pct: 0.001 } }
      - { class: DrawdownPenaltyTerm, kwargs: { weight: 0.25 } }

observation:
  class: StackedObservationBuilder
  module_path: aqp.rl.core.observation
  kwargs:
    builders:
      - class: TechnicalIndicatorBuilder
        kwargs: { indicators: [macd, rsi_30, sma_20] }
      - class: TurbulenceBuilder
        kwargs: { lookback: 252 }

agent:
  class: SB3Adapter
  module_path: aqp.rl.agents.sb3_adapter
  kwargs:
    algorithm: PPO
    policy: MlpPolicy
    learning_rate: 3.0e-4
    n_steps: 2048

training:
  total_timesteps: 200000
  log_interval: 10
  seed: 42

evaluation:
  start: "2023-07-01"
  end: "2024-01-01"
  episodes: 1

ensembler: null

trajectory_store:
  class: IcebergTrajectoryStore
  module_path: aqp.rl.trajectories.iceberg_writer
  kwargs:
    flush_every: 1000

mlflow:
  experiment: aqp-rl
  register_model_as: rl-ppo-portfolio
```

Snapshotting
------------

:meth:`snapshot_hash` returns SHA256 of the canonical JSON form (sorted
keys, no whitespace). Persisting via
:func:`aqp.rl.registry.persist_spec` writes a new
:class:`RLExperimentVersion` row whenever the hash changes.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


RLSpecKind = Literal["training", "evaluation", "paper", "research", "ensemble"]
"""Discriminator for the kind of run the spec describes."""


# ---------------------------------------------------------------------------
# Sub-spec dataclasses
# ---------------------------------------------------------------------------


class UniverseRef(BaseModel):
    """Universe over which the env operates."""

    symbols: list[str] = Field(default_factory=list)
    model: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataPipelineRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.data.BaseDataPipeline` build-spec.

    Either an inline ``{class, module_path, kwargs}`` block or a named
    preset (``preset: "iceberg-default"``) resolved from
    :mod:`aqp.rl.data_pipelines.presets`.
    """

    preset: str | None = None
    spec: dict[str, Any] | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class TrainingConfig(BaseModel):
    total_timesteps: int = 100_000
    log_interval: int = 10
    seed: int | None = None
    n_envs: int = 1
    eval_during_training: bool = False
    eval_freq: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class EvaluationConfig(BaseModel):
    start: str | None = None
    end: str | None = None
    episodes: int = 1
    deterministic: bool = True
    extras: dict[str, Any] = Field(default_factory=dict)


class EnsemblerRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.ensembler.BaseEnsembler` build-spec."""

    spec: dict[str, Any] | None = None
    members: list[dict[str, Any]] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class TrajectoryStoreRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.replay.BaseTrajectoryStore` build-spec."""

    spec: dict[str, Any] | None = None
    enabled: bool = True


class MLflowConfig(BaseModel):
    experiment: str | None = None
    register_model_as: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class RewardRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.reward.BaseRewardModel` build-spec."""

    spec: dict[str, Any] | None = None


class ObservationRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.observation.BaseObservationBuilder` build-spec."""

    spec: dict[str, Any] | None = None


class ActionRef(BaseModel):
    """Reference to a :class:`aqp.rl.core.action.BaseActionSpace` build-spec."""

    spec: dict[str, Any] | None = None


class TerminationRef(BaseModel):
    """Reference to a list of :class:`aqp.rl.core.termination.BaseTerminationCondition` specs."""

    specs: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RLExperimentSpec
# ---------------------------------------------------------------------------


class RLExperimentSpec(BaseModel):
    """Declarative blueprint for one RL experiment.

    Hash-locked: the runtime persists snapshots into
    ``rl_experiment_versions`` keyed on :meth:`snapshot_hash`.
    """

    name: str
    slug: str = ""
    kind: RLSpecKind = "training"
    description: str = ""

    universe: UniverseRef = Field(default_factory=UniverseRef)
    data_pipeline: DataPipelineRef | None = None

    env: dict[str, Any] | None = None
    reward: RewardRef | None = None
    observation: ObservationRef | None = None
    action: ActionRef | None = None
    terminations: TerminationRef = Field(default_factory=TerminationRef)

    agent: dict[str, Any] | None = None

    training: TrainingConfig = Field(default_factory=TrainingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    ensembler: EnsemblerRef | None = None
    trajectory_store: TrajectoryStoreRef = Field(default_factory=TrajectoryStoreRef)

    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)

    annotations: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------ validation

    @model_validator(mode="after")
    def _ensure_slug(self) -> RLExperimentSpec:
        if not self.slug:
            self.slug = _slugify(self.name) if self.name else ""
        else:
            self.slug = _slugify(self.slug)
        return self

    @field_validator("annotations", mode="before")
    @classmethod
    def _coerce_annotations(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    # ------------------------------------------------------------------ snapshotting

    def snapshot_hash(self) -> str:
        """SHA256 over the canonical JSON form (sorted keys, no whitespace)."""
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ YAML helpers

    @classmethod
    def from_yaml_path(cls, path: str) -> RLExperimentSpec:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> RLExperimentSpec:
        data = yaml.safe_load(content) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def load_specs_from_dir(dir_path: str, *, suffix: str = ".yaml") -> Iterable[RLExperimentSpec]:
    """Yield every RL experiment spec yaml under ``dir_path`` (recursively)."""
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.rglob(f"*{suffix}")):
        try:
            yield RLExperimentSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "ActionRef",
    "DataPipelineRef",
    "EnsemblerRef",
    "EvaluationConfig",
    "MLflowConfig",
    "ObservationRef",
    "RLExperimentSpec",
    "RLSpecKind",
    "RewardRef",
    "TerminationRef",
    "TrainingConfig",
    "TrajectoryStoreRef",
    "UniverseRef",
    "load_specs_from_dir",
]
