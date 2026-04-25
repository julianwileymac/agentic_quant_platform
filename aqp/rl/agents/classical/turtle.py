"""Turtle trading agent (N-day high / low breakout)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.registry import agent
from aqp.rl.agents.classical.base import Action, BaseClassicalAgent


@agent("TurtleAgent", tags=("classical", "breakout", "turtle"))
class TurtleAgent(BaseClassicalAgent):
    """Donchian-channel breakout, FinRL / Huseinzol05 flavour."""

    name = "turtle"

    def __init__(
        self,
        entry_window: int = 20,
        exit_window: int = 10,
        initial_cash: float = 100_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self.entry_window = int(entry_window)
        self.exit_window = int(exit_window)

    def decide(self, price: float, row: pd.Series, state: dict[str, Any]) -> Action:
        hist = state["history"]
        if len(hist) <= self.entry_window:
            return Action.HOLD
        recent_entry = hist[-(self.entry_window + 1) : -1]
        recent_exit = hist[-(self.exit_window + 1) : -1]
        if price > max(recent_entry) and self.shares == 0:
            return Action.BUY
        if price < min(recent_exit) and self.shares > 0:
            return Action.SELL
        return Action.HOLD


__all__ = ["TurtleAgent"]
