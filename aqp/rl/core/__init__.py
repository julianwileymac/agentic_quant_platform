"""Core RL abstractions — the metaclass-driven base classes that every
concrete env / agent / reward / observation / data pipeline plugs into.

Public surface mirrors :mod:`aqp.bots.spec` + :mod:`aqp.bots.runtime`: the
core defines *contracts* (abstract bases + a uniform registration
metaclass) while the concrete presets under
:mod:`aqp.rl.envs`, :mod:`aqp.rl.rewards`, :mod:`aqp.rl.observations`,
:mod:`aqp.rl.actions`, :mod:`aqp.rl.terminations`,
:mod:`aqp.rl.data_pipelines`, :mod:`aqp.rl.agents`,
:mod:`aqp.rl.ensemblers`, :mod:`aqp.rl.experiments` ship the
implementations.

The metaclass tags each subclass with a ``rl_kind`` so the API
introspection routes (``GET /rl/components/{kind}``) can enumerate
everything browseable from the UI.
"""
from __future__ import annotations

from aqp.rl.core.action import (
    BaseActionSpace,
    ContinuousWeightsAction,
    DiscreteBuySellHoldAction,
    IntegerSharesAction,
    MultiDiscreteAction,
    SoftmaxWeightsAction,
    TargetPositionAction,
)
from aqp.rl.core.base import (
    RL_KIND_ACTION,
    RL_KIND_AGENT,
    RL_KIND_DATA,
    RL_KIND_ENSEMBLER,
    RL_KIND_ENV,
    RL_KIND_EXPERIMENT,
    RL_KIND_OBSERVATION,
    RL_KIND_POLICY,
    RL_KIND_REWARD,
    RL_KIND_TERMINATION,
    RL_KIND_TRAJECTORY_STORE,
    RL_KINDS,
    RLComponent,
    RLComponentMeta,
    list_rl_components,
    rl_kind_for,
)
from aqp.rl.core.data import BaseDataPipeline
from aqp.rl.core.ensembler import BaseEnsembler
from aqp.rl.core.env import BaseRLEnv
from aqp.rl.core.experiment import BaseExperiment
from aqp.rl.core.observation import BaseObservationBuilder, StackedObservationBuilder
from aqp.rl.core.policy import BasePolicy, BaseRLAgent
from aqp.rl.core.replay import BaseReplayBuffer, BaseTrajectoryStore, InMemoryReplayBuffer
from aqp.rl.core.reward import BaseRewardModel, CompositeReward, RewardTerm
from aqp.rl.core.schemas import component_schema, list_component_schemas
from aqp.rl.core.termination import BaseTerminationCondition

__all__ = [
    "RL_KINDS",
    "RL_KIND_ACTION",
    "RL_KIND_AGENT",
    "RL_KIND_DATA",
    "RL_KIND_ENSEMBLER",
    "RL_KIND_ENV",
    "RL_KIND_EXPERIMENT",
    "RL_KIND_OBSERVATION",
    "RL_KIND_POLICY",
    "RL_KIND_REWARD",
    "RL_KIND_TERMINATION",
    "RL_KIND_TRAJECTORY_STORE",
    "BaseActionSpace",
    "BaseDataPipeline",
    "BaseEnsembler",
    "BaseExperiment",
    "BaseObservationBuilder",
    "BasePolicy",
    "BaseReplayBuffer",
    "BaseRLAgent",
    "BaseRLEnv",
    "BaseRewardModel",
    "BaseTerminationCondition",
    "BaseTrajectoryStore",
    "CompositeReward",
    "ContinuousWeightsAction",
    "DiscreteBuySellHoldAction",
    "InMemoryReplayBuffer",
    "IntegerSharesAction",
    "MultiDiscreteAction",
    "RLComponent",
    "RLComponentMeta",
    "RewardTerm",
    "SoftmaxWeightsAction",
    "StackedObservationBuilder",
    "TargetPositionAction",
    "component_schema",
    "list_component_schemas",
    "list_rl_components",
    "rl_kind_for",
]
