"""Moving-average crossover agent."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import agent
from aqp.rl.agents.classical.base import Action, BaseClassicalAgent


@agent("MovingAverageAgent", tags=("classical", "moving-average"))
class MovingAverageAgent(BaseClassicalAgent):
    """Buy when the fast SMA crosses above the slow SMA, sell when it reverses."""

    name = "moving_average"

    def __init__(
        self,
        fast_window: int = 9,
        slow_window: int = 21,
        initial_cash: float = 100_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self.fast_window = int(fast_window)
        self.slow_window = int(slow_window)

    def decide(self, price: float, row: pd.Series, state: dict[str, Any]) -> Action:
        hist = state["history"]
        if len(hist) < self.slow_window + 1:
            return Action.HOLD
        hist_arr = np.asarray(hist)
        fast_now = hist_arr[-self.fast_window :].mean()
        slow_now = hist_arr[-self.slow_window :].mean()
        fast_prev = hist_arr[-self.fast_window - 1 : -1].mean()
        slow_prev = hist_arr[-self.slow_window - 1 : -1].mean()
        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now
        if crossed_up and self.shares == 0:
            return Action.BUY
        if crossed_down and self.shares > 0:
            return Action.SELL
        return Action.HOLD


__all__ = ["MovingAverageAgent"]
