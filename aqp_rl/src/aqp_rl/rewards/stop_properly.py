"""``StopProperlyShaping`` — port of NeMo-RL's ``stop_properly_penalty_coef``.

NeMo-RL applies the penalty in
:func:`nemo_rl.algorithms.reward_functions.apply_reward_shaping`
(commit 20d46a7d1bd987df1c89b3c5a81dc945c3d201e4)::

    rewards = torch.where(truncated, rewards * stop_properly_penalty_coef, rewards)

with ``coef in [0, 1]``. The coefficient discounts the rewards of
trajectories that failed to "stop properly" (in NLP: ran past
max_response_length without emitting EOS; in AQP: blew a hard risk
limit before the temporal window closed).

The AQP port wraps any underlying :class:`RewardTerm` or
:class:`BaseRewardModel` and reads ``info['truncated']`` (set by the
env's step driver when a hard-breach :class:`BaseTerminationCondition`
with ``truncates_episode=True`` fires).

Two adapter shapes are exposed:

- :class:`StopProperlyPenaltyTerm` — a :class:`RewardTerm` you can
  drop into any existing :class:`CompositeReward` so the truncation
  penalty composes alongside PnL / turnover / drawdown terms.
- :class:`StopProperlyWrapper` — a :class:`BaseRewardModel` that
  wraps an inner reward model and intercepts the final scalar.

Both honour the canonical ``coef in [0, 1]`` semantics: ``0`` =
draconian zeroing of truncated rewards; ``1`` = no penalty.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import BaseRewardModel, RewardTerm

logger = logging.getLogger(__name__)


def _coerce_coef(value: float) -> float:
    coef = float(value)
    if not 0.0 <= coef <= 1.0:
        raise ValueError(
            f"stop_properly_penalty_coef must be in [0, 1]; got {coef!r}"
        )
    return coef


class StopProperlyPenaltyTerm(RewardTerm):
    """Composable penalty term that scales rewards on truncated steps.

    On any step where ``info['truncated']`` is truthy the term
    contributes the negative discount ``-(1 - coef) * |reward_total|``
    so the net per-step reward of the composite collapses by the
    expected amount. By itself it does not access the underlying
    reward magnitude — instead it relies on ``info['reward_total']``
    being populated by the outer composite, OR on
    ``info['pnl']`` / ``info['portfolio_value']`` as a heuristic
    proxy.

    The cleaner pattern for most users is :class:`StopProperlyWrapper`
    which intercepts the scalar BaseRewardModel output directly.
    """

    rl_alias: ClassVar[str] = "StopProperlyPenaltyTerm"
    rl_source: ClassVar[str] = "nemo_rl"
    rl_category: ClassVar[str] = "risk"
    rl_tags: ClassVar[tuple[str, ...]] = ("stop_properly", "truncation", "finrl_x")

    def __init__(
        self,
        *,
        coef: float = 0.0,
        weight: float = 1.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name or "stop_properly_penalty", weight=weight)
        self.coef = _coerce_coef(coef)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        if not bool(info.get("truncated")):
            return 0.0
        # NeMo-RL formula: shaped = rewards * coef. The composite has
        # already summed its other terms — we contribute -(1-coef) of
        # whatever proxy magnitude is available so the net step
        # reward effectively equals the coef * other_terms.
        magnitude = float(
            info.get("reward_total")
            or info.get("pnl")
            or (float(next_state.get("portfolio_value", 0.0)) - float(state.get("portfolio_value", 0.0)))
        )
        return -(1.0 - self.coef) * abs(magnitude)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update({"coef": self.coef})
        return out


class StopProperlyWrapper(BaseRewardModel):
    """Wraps a reward model and applies the truncation penalty post-hoc.

    Mirrors NeMo-RL's ``apply_reward_shaping`` more closely than the
    per-term variant. On every step:

    1. Delegate to the inner model to compute the raw reward + per-term
       decomposition.
    2. If ``info['truncated']`` is truthy, scale the reward AND every
       per-term contribution by ``coef`` so the decomposition still sums
       to the shaped scalar.
    3. Stash the original (pre-penalty) reward on
       ``info['stop_properly_original_reward']`` so dashboards can
       quantify the regret.
    """

    rl_alias: ClassVar[str] = "StopProperlyWrapper"
    rl_source: ClassVar[str] = "nemo_rl"
    rl_category: ClassVar[str] = "shaped"
    rl_tags: ClassVar[tuple[str, ...]] = ("stop_properly", "truncation", "finrl_x")

    def __init__(
        self,
        *,
        inner: BaseRewardModel,
        coef: float = 0.0,
    ) -> None:
        if not isinstance(inner, BaseRewardModel):
            raise TypeError(
                f"StopProperlyWrapper expects a BaseRewardModel, got {type(inner).__name__}"
            )
        self.inner = inner
        self.coef = _coerce_coef(coef)

    def reset(self) -> None:
        self.inner.reset()

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        raw = float(self.inner.compute(state, action, next_state, info))
        if not bool(info.get("truncated")):
            return raw
        shaped = raw * self.coef
        if isinstance(info, dict):
            info["stop_properly_original_reward"] = raw
            info["stop_properly_coef"] = self.coef
            # Scale per-term contributions so the decomposition still sums.
            terms = info.get("reward_terms")
            if isinstance(terms, dict):
                info["reward_terms"] = {k: float(v) * self.coef for k, v in terms.items()}
        logger.debug(
            "StopProperlyWrapper: truncated step shaped %.6f -> %.6f (coef=%.3f)",
            raw,
            shaped,
            self.coef,
        )
        return shaped

    def decomposition(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> dict[str, float]:
        base = self.inner.decomposition(state, action, next_state, info)
        if not bool(info.get("truncated")):
            return base
        return {k: float(v) * self.coef for k, v in base.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "module_path": "aqp_rl.rewards.stop_properly",
            "kwargs": {
                "inner": self.inner.to_dict() if hasattr(self.inner, "to_dict") else {},
                "coef": self.coef,
            },
        }


__all__ = [
    "StopProperlyPenaltyTerm",
    "StopProperlyWrapper",
]
