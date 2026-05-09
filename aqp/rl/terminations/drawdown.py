"""Drawdown-based early termination."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.termination import BaseTerminationCondition


class DrawdownTermination(BaseTerminationCondition):
    """End the episode if drawdown breaches ``-max_drawdown_pct``."""

    rl_alias: ClassVar[str] = "DrawdownTermination"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, max_drawdown_pct: float = 0.5) -> None:
        super().__init__(name="drawdown_termination")
        self.max_drawdown_pct = float(max_drawdown_pct)

    def check(self, idx: int, horizon: int, env_state: Mapping[str, Any]) -> bool:
        peak = float(env_state.get("peak", 0.0) or 0.0)
        pv = float(env_state.get("portfolio_value", peak) or peak)
        if peak <= 0:
            return False
        dd = (pv - peak) / peak
        return dd <= -self.max_drawdown_pct


__all__ = ["DrawdownTermination"]
