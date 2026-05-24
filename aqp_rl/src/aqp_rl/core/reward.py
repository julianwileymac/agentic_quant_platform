"""Reward modelling — composable :class:`RewardTerm` primitives + composite.

Every concrete reward term inherits :class:`RewardTerm`, declares its
``name`` + ``weight`` and implements
:meth:`compute(state, action, next_state, info) -> float`. The
:class:`CompositeReward` sums weighted terms and emits per-term
contributions into ``info["reward_terms"]`` so the UI's
reward-decomposition chart can plot each component over time.

This mirrors the pattern recommended in the FinRL paper trading work
(``default_reward = pnl - turnover_cost - drawdown_penalty``) but lets
researchers swap in any combination from the registered library
(``aqp/rl/rewards/``) — the env never hard-codes the formula.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar, Mapping

from aqp_rl.core.base import RL_KIND_REWARD, RLComponent


class RewardTerm(RLComponent):
    """One additive component of a composite reward.

    A term has:

    - ``name``: short identifier persisted to ``rl.reward_decomposition``
      and shown in the UI legend.
    - ``weight``: scalar multiplier applied to :meth:`compute`'s output.
      Negative weights make the term a penalty, positive weights make it
      a bonus.
    - :meth:`compute` returns a *raw* contribution (the composite
      multiplies by ``weight`` before summing).
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_REWARD

    def __init__(self, *, name: str | None = None, weight: float = 1.0) -> None:
        self.name = name or self.__class__.__name__
        self.weight = float(weight)

    @abstractmethod
    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:  # pragma: no cover - abstract
        """Compute the raw (unweighted) reward contribution for one step."""

    def reset(self) -> None:
        """Hook for stateful terms (rolling Sharpe, episode buffers).

        Default is a no-op — most terms are pure functions of the
        current step.
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "name": self.name,
            "weight": self.weight,
        }


class BaseRewardModel(RLComponent):
    """Reward model contract — produce a scalar reward for the env step.

    The two well-known concrete implementations are:

    - :class:`CompositeReward` — sum of weighted :class:`RewardTerm`s
      (default for the new abstract envs).
    - ``LegacyReward`` — wraps a free function (kept for backwards-
      compatibility with the existing :func:`default_reward`).
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_REWARD

    @abstractmethod
    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:  # pragma: no cover - abstract
        """Compute the scalar reward for a single env step."""

    def reset(self) -> None:
        """Reset any internal state at episode boundary."""

    def decomposition(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> dict[str, float]:
        """Optional: return per-term breakdown for the UI / Iceberg log.

        Returns ``{term_name: weighted_contribution}``. Default returns a
        single ``{"total": compute(...)}`` entry so even simple reward
        models expose a structured payload.
        """
        return {"total": float(self.compute(state, action, next_state, info))}


class CompositeReward(BaseRewardModel):
    """Sum of weighted :class:`RewardTerm`s.

    Stores per-term weighted contributions in
    ``info["reward_terms"]`` so the runtime can persist them to the
    ``rl.reward_decomposition`` Iceberg table.
    """

    rl_alias: ClassVar[str] = "CompositeReward"
    rl_tags: ClassVar[tuple[str, ...]] = ("composite",)
    rl_source: ClassVar[str] = "aqp"

    def __init__(self, terms: list[RewardTerm | dict[str, Any]] | None = None) -> None:
        from aqp.core.registry import build_from_config

        resolved: list[RewardTerm] = []
        for t in terms or []:
            if isinstance(t, RewardTerm):
                resolved.append(t)
            elif isinstance(t, dict) and "class" in t:
                obj = build_from_config(t)
                if not isinstance(obj, RewardTerm):
                    raise TypeError(
                        f"CompositeReward expects RewardTerm subclasses, got {type(obj)}"
                    )
                resolved.append(obj)
            else:
                raise TypeError(f"Unsupported term spec: {type(t).__name__}")
        self.terms = resolved
        self._last_breakdown: dict[str, float] = {}

    def reset(self) -> None:
        for t in self.terms:
            t.reset()
        self._last_breakdown = {}

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        total = 0.0
        breakdown: dict[str, float] = {}
        for term in self.terms:
            raw = float(term.compute(state, action, next_state, info))
            weighted = term.weight * raw
            breakdown[term.name] = weighted
            total += weighted
        self._last_breakdown = breakdown
        if isinstance(info, dict):
            info.setdefault("reward_terms", {}).update(breakdown)
        return float(total)

    def decomposition(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> dict[str, float]:
        if self._last_breakdown:
            return dict(self._last_breakdown)
        self.compute(state, action, next_state, info)
        return dict(self._last_breakdown)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": "CompositeReward",
            "module_path": "aqp_rl.core.reward",
            "kwargs": {"terms": [t.to_dict() for t in self.terms]},
        }


__all__ = [
    "BaseRewardModel",
    "CompositeReward",
    "RewardTerm",
]
