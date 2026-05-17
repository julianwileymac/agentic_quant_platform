"""Advantage estimators — first-class RL components (``rl_advantage_estimator``).

Native ports of the NVIDIA-NeMo/RL primitives the FinRL-X blueprint
relies on:

- :class:`ReinforcePlusPlusAdvantage` — leave-one-out cohort baseline
  with decoupled global normalisation (NeMo-RL
  ``algorithms/utils.py::calculate_baseline_and_std_per_prompt`` +
  ``masked_mean(..., global_normalization_factor=...)``). The
  ``minus_baseline`` flag and the local-vs-global decoupling are the
  key innovation that stabilises training in highly non-stationary
  financial markets — see ProRLv2 paper for the math.
- :class:`GRPOAdvantage` — Group Relative Policy Optimization
  (DeepSeek R1 / NeMo-RL ``algorithms/grpo.py``). No critic; baseline
  is the cohort mean reward. Cheaper memory profile than PPO+critic
  while still using the cohort relative signal.
- :class:`GAEAdvantage` — vanilla Generalised Advantage Estimation
  (Schulman 2016) for parity with the legacy SB3 / CleanRL PPO path.

All three subclass :class:`BaseAdvantageEstimator` and register via
the :class:`RLComponentMeta` metaclass (``rl_kind="rl_advantage_estimator"``).
The :class:`RLExperimentSpec.advantage` field references them by
``rl_alias``.
"""
from __future__ import annotations

from aqp.rl.advantage.base import AdvantageOutput, BaseAdvantageEstimator
from aqp.rl.advantage.gae import GAEAdvantage
from aqp.rl.advantage.grpo import GRPOAdvantage
from aqp.rl.advantage.reinforce_plus_plus import ReinforcePlusPlusAdvantage

__all__ = [
    "AdvantageOutput",
    "BaseAdvantageEstimator",
    "GAEAdvantage",
    "GRPOAdvantage",
    "ReinforcePlusPlusAdvantage",
]
