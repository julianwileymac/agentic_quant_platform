"""ABCD strategy agent (chart-pattern heuristic)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import agent
from aqp.rl.agents.classical.base import Action, BaseClassicalAgent


@agent("ABCDStrategyAgent", tags=("classical", "pattern", "abcd"))
class ABCDStrategyAgent(BaseClassicalAgent):
    """Buy when a 4-point A→B→C→D pattern forms (A low, B high, C > A, D
    within range). Sell on break below the recent swing low.
    """

    name = "abcd"

    def __init__(
        self,
        lookback: int = 30,
        min_leg: float = 0.02,
        initial_cash: float = 100_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self.lookback = int(lookback)
        self.min_leg = float(min_leg)

    def decide(self, price: float, row: pd.Series, state: dict[str, Any]) -> Action:
        hist = state["history"]
        if len(hist) < self.lookback:
            return Action.HOLD
        window = np.asarray(hist[-self.lookback :])
        a = float(window.min())
        b = float(window.max())
        midpoint = a + (b - a) / 2.0
        leg_ab = (b - a) / max(a, 1e-8)
        if leg_ab < self.min_leg:
            return Action.HOLD
        # ABCD-long trigger: recent low above A's level AND price reclaiming midpoint.
        if self.shares == 0 and price > midpoint and window[-1] > window[-2]:
            return Action.BUY
        if self.shares > 0 and price < a:
            return Action.SELL
        return Action.HOLD


__all__ = ["ABCDStrategyAgent"]
