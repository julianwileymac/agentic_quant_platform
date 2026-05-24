"""Shared base class + action-enum for classical rule-based agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import numpy as np
import pandas as pd


class Action(IntEnum):
    """Discrete action set used by every classical agent."""

    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass
class TradeLog:
    """Running record of the agent's decisions."""

    buys: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    sells: list[tuple[pd.Timestamp, float]] = field(default_factory=list)
    equity: list[tuple[pd.Timestamp, float]] = field(default_factory=list)

    def record_buy(self, ts: pd.Timestamp, price: float) -> None:
        self.buys.append((ts, float(price)))

    def record_sell(self, ts: pd.Timestamp, price: float) -> None:
        self.sells.append((ts, float(price)))

    def record_equity(self, ts: pd.Timestamp, pv: float) -> None:
        self.equity.append((ts, float(pv)))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.equity, columns=["timestamp", "equity"]).set_index("timestamp")


class BaseClassicalAgent(ABC):
    """Classical rule-based agent.

    Implement :meth:`decide` for a single bar, and :meth:`run` will drive
    a full back-run with a naive long-flat cash/inventory book.
    """

    name: str = "classical"

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        self.initial_cash = float(initial_cash)
        self.reset()

    def reset(self) -> None:
        self.cash: float = self.initial_cash
        self.shares: int = 0
        self.log = TradeLog()
        self._history: list[float] = []

    @abstractmethod
    def decide(self, price: float, row: pd.Series, state: dict[str, Any]) -> Action:
        """Return a :class:`Action` given the latest bar + ad-hoc state."""

    def run(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Execute over a bars frame; returns the equity-curve frame."""
        self.reset()
        if bars.empty:
            return self.log.to_frame()
        state: dict[str, Any] = {"history": [], "entry": None}
        for ts, row in bars.iterrows():
            price = float(row["close"])
            state["history"].append(price)
            self._history.append(price)
            action = self.decide(price, row, state)
            if action == Action.BUY and self.cash >= price:
                n = int(self.cash // price)
                if n > 0:
                    self.cash -= n * price
                    self.shares += n
                    state["entry"] = price
                    self.log.record_buy(ts, price)
            elif action == Action.SELL and self.shares > 0:
                self.cash += self.shares * price
                self.log.record_sell(ts, price)
                self.shares = 0
                state["entry"] = None
            pv = self.cash + self.shares * price
            self.log.record_equity(ts, pv)
        return self.log.to_frame()


__all__ = ["Action", "BaseClassicalAgent", "TradeLog"]
