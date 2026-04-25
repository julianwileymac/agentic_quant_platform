"""Signal rolling agent — buy/sell on rolling-std breakouts."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import agent
from aqp.rl.agents.classical.base import Action, BaseClassicalAgent


@agent("SignalRollingAgent", tags=("classical", "rolling"))
class SignalRollingAgent(BaseClassicalAgent):
    """Buy when price is ``buy_k`` stdev below the rolling mean, sell when
    ``sell_k`` stdev above.
    """

    name = "signal_rolling"

    def __init__(
        self,
        window: int = 30,
        buy_k: float = 1.0,
        sell_k: float = 1.0,
        initial_cash: float = 100_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self.window = int(window)
        self.buy_k = float(buy_k)
        self.sell_k = float(sell_k)

    def decide(self, price: float, row: pd.Series, state: dict[str, Any]) -> Action:
        hist = state["history"]
        if len(hist) < self.window + 1:
            return Action.HOLD
        window = np.asarray(hist[-self.window :])
        mean = float(window.mean())
        std = float(window.std() + 1e-12)
        if price < mean - self.buy_k * std and self.shares == 0:
            return Action.BUY
        if price > mean + self.sell_k * std and self.shares > 0:
            return Action.SELL
        return Action.HOLD


__all__ = ["SignalRollingAgent"]
