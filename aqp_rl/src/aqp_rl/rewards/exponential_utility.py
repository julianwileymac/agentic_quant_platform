"""Exponential (CARA) utility reward.

Reward = ``−exp(−γ · ΔPnL)`` where ``γ > 0`` is the absolute risk
aversion coefficient. As ``γ → 0`` the reward degenerates to the
linear PnL (up to scaling); as ``γ`` grows the agent becomes
increasingly loss-averse.

The Constant Absolute Risk Aversion (CARA) utility shows up in the
classical Avellaneda-Stoikov market-maker derivation and the
Carmona-Webster optimal-execution literature. Most useful when:

- The agent is allowed unbounded losses (without a CARA-style floor a
  pure-PnL reward can be saturation-resistant in tail regimes).
- The user wants to compare an RL policy against the closed-form
  CARA-optimal benchmark.

Hard rule 19: registered through :class:`RLComponent` metaclass with
``rl_alias='exp_utility'``.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class ExponentialUtility(RewardTerm):
    """Per-step exponential utility reward.

    Parameters
    ----------
    weight:
        Composite multiplier.
    gamma:
        Absolute risk-aversion coefficient ``γ > 0``. Larger ⇒ more
        loss-averse. Default ``0.1``.
    pnl_scale:
        Pre-scaler applied to ``ΔPnL`` before the exponential to avoid
        ``exp(−γ · ΔPnL)`` saturating for large step PnLs. Default
        ``1e-2`` (i.e. PnL is expressed in percentage of starting
        portfolio).
    clip_pnl:
        Optional symmetric clip applied to ``ΔPnL`` before the
        exponential. Defends against numerical overflow when a single
        step produces an unrealistically large PnL (e.g. flash crash
        in a buggy env). ``None`` disables clipping.
    """

    rl_alias: ClassVar[str] = "exp_utility"
    rl_source: ClassVar[str] = "cara"
    rl_category: ClassVar[str] = "risk"
    rl_tags: ClassVar[tuple[str, ...]] = ("cara", "exponential_utility", "loss_averse")

    def __init__(
        self,
        *,
        weight: float = 1.0,
        gamma: float = 0.1,
        pnl_scale: float = 1e-2,
        clip_pnl: float | None = 100.0,
    ) -> None:
        if gamma <= 0:
            raise ValueError(f"ExponentialUtility gamma must be > 0; got {gamma!r}")
        super().__init__(name="exp_utility", weight=weight)
        self.gamma = float(gamma)
        self.pnl_scale = float(pnl_scale)
        self.clip_pnl = float(clip_pnl) if clip_pnl is not None else None

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev_pv = float(state.get("portfolio_value", 0.0) or 0.0)
        curr_pv = float(next_state.get("portfolio_value", prev_pv) or prev_pv)
        pnl = (curr_pv - prev_pv) * self.pnl_scale
        if self.clip_pnl is not None:
            pnl = max(-self.clip_pnl, min(self.clip_pnl, pnl))
        return float(-math.exp(-self.gamma * pnl))

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "gamma": self.gamma,
                "pnl_scale": self.pnl_scale,
                "clip_pnl": self.clip_pnl,
            }
        )
        return out


__all__ = ["ExponentialUtility"]
