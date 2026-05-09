"""PnL-flavoured reward terms.

Mirrors FinRL's ``reward = end_total_asset - begin_total_asset`` (with
optional log-return scaling).
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Mapping

from aqp.rl.core.reward import RewardTerm


class PnLTerm(RewardTerm):
    """Raw portfolio-value delta: ``pv_t - pv_{t-1}``.

    The composite ``weight`` (typically 1.0) keeps this in absolute
    dollars; multiply by a small ``reward_scaling`` (e.g. 1e-4) to
    keep gradients well-conditioned.
    """

    rl_alias: ClassVar[str] = "PnLTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "pnl"

    def __init__(self, *, weight: float = 1.0, scale: float = 1e-4) -> None:
        super().__init__(name="pnl", weight=weight)
        self.scale = float(scale)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        return float((curr - prev) * self.scale)


class LogReturnTerm(RewardTerm):
    """Log-return ``log(pv_t / pv_{t-1})``.

    Scale-free, well-behaved across orders of magnitude — the canonical
    reward for FinRL's discrete single-stock env (with optional cash
    penalty applied alongside).
    """

    rl_alias: ClassVar[str] = "LogReturnTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "pnl"

    def __init__(self, *, weight: float = 1.0) -> None:
        super().__init__(name="log_return", weight=weight)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        if prev <= 0 or curr <= 0:
            return 0.0
        return float(math.log(curr / prev))


__all__ = ["LogReturnTerm", "PnLTerm"]
