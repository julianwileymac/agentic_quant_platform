"""Cointegration-based pairs trading alpha.

Given two symbols, compute the hedge-ratio spread via rolling OLS and
emit long/short signals on the **spread** (long one leg / short the other)
whenever the spread's z-score breaches an entry threshold.

Inspired by Lean's ``BasePairsTradingAlphaModel`` and ML4T Ch 9.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("PairsTradingAlphaModel")
class PairsTradingAlphaModel(IAlphaModel):
    """Mean-reversion on the hedge-ratio spread of two instruments."""

    def __init__(
        self,
        symbol_a: str,
        symbol_b: str,
        lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
    ) -> None:
        self.symbol_a = str(symbol_a)
        self.symbol_b = str(symbol_b)
        self.lookback = int(lookback)
        self.entry_z = float(entry_z)
        self.exit_z = float(exit_z)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        now = context.get("current_time")
        a_vt = self._match(self.symbol_a, universe)
        b_vt = self._match(self.symbol_b, universe)
        if a_vt is None or b_vt is None:
            return []
        pivot = (
            bars[bars["vt_symbol"].isin({a_vt, b_vt})]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .dropna()
        )
        if a_vt not in pivot.columns or b_vt not in pivot.columns:
            return []
        if len(pivot) < self.lookback:
            return []
        window = pivot.iloc[-self.lookback :]
        a = window[a_vt].values
        b = window[b_vt].values
        # Hedge ratio = OLS slope of a on b (no intercept)
        if np.dot(b, b) == 0:
            return []
        beta = np.dot(a, b) / np.dot(b, b)
        spread = a - beta * b
        mean = spread.mean()
        std = spread.std(ddof=1)
        if std == 0:
            return []
        z = (spread[-1] - mean) / std
        if abs(z) < self.entry_z:
            return []
        # z > entry_z -> spread is too wide → short A, long B
        # z < -entry_z -> spread is too narrow → long A, short B
        direction_a = Direction.SHORT if z > 0 else Direction.LONG
        direction_b = Direction.LONG if z > 0 else Direction.SHORT
        strength = float(min(1.0, abs(z) / (self.entry_z * 2)))
        return [
            Signal(
                symbol=Symbol.parse(a_vt),
                strength=strength,
                direction=direction_a,
                timestamp=now or window.index[-1].to_pydatetime(),
                confidence=0.65,
                source="PairsTradingAlphaModel",
                rationale=f"spread z={z:.2f}, beta={beta:.3f}",
            ),
            Signal(
                symbol=Symbol.parse(b_vt),
                strength=strength,
                direction=direction_b,
                timestamp=now or window.index[-1].to_pydatetime(),
                confidence=0.65,
                source="PairsTradingAlphaModel",
                rationale=f"pair-leg z={z:.2f}, beta={beta:.3f}",
            ),
        ]

    def _match(self, ticker: str, universe: list[Symbol]) -> str | None:
        ticker = ticker.upper()
        for s in universe:
            if s.ticker.upper() == ticker or s.vt_symbol.upper() == ticker:
                return s.vt_symbol
        return None
