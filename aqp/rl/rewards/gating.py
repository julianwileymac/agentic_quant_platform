"""Risk-state gating reward terms.

Mirrors FinRL's turbulence-threshold liquidation in ``StockTradingEnv``
(no reward when turbulence > threshold ⇒ flatten positions).
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.reward import RewardTerm


class TurbulenceGateTerm(RewardTerm):
    """Apply a fixed penalty whenever turbulence exceeds the threshold."""

    rl_alias: ClassVar[str] = "TurbulenceGateTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk_gate"

    def __init__(
        self,
        *,
        weight: float = 1.0,
        threshold: float = 140.0,
        penalty: float = 1.0,
    ) -> None:
        super().__init__(name="turbulence_gate", weight=weight)
        self.threshold = float(threshold)
        self.penalty = float(penalty)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        turbulence = float(info.get("turbulence", 0.0) or 0.0)
        if turbulence > self.threshold:
            return float(-self.penalty)
        return 0.0


class MarginCallTerm(RewardTerm):
    """Large negative reward if portfolio breaches a margin requirement."""

    rl_alias: ClassVar[str] = "MarginCallTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk_gate"

    def __init__(
        self,
        *,
        weight: float = 1.0,
        max_drawdown_pct: float = -0.5,
        penalty: float = 100.0,
    ) -> None:
        super().__init__(name="margin_call", weight=weight)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.penalty = float(penalty)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        dd = float(info.get("drawdown", 0.0) or 0.0)
        if dd <= self.max_drawdown_pct:
            return float(-self.penalty)
        return 0.0


__all__ = ["MarginCallTerm", "TurbulenceGateTerm"]
