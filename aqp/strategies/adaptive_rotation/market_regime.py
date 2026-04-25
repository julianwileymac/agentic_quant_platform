"""Lightweight market-regime classifier.

Returns ``risk_on | neutral | risk_off`` from index momentum + recent
volatility. We intentionally keep this simple — the full reference
implementation supports HMM and clustering modes; here we ship the
deterministic z-score baseline that's robust enough for backtests.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


Regime = Literal["risk_on", "neutral", "risk_off"]


class MarketRegimeClassifier:
    """Classify the current regime from a benchmark price series.

    Inputs the closing prices of the benchmark (e.g. SPY) and emits a
    label by combining:

    - 60-day momentum (price / 60d moving average - 1)
    - 20-day realised volatility (annualised)

    Thresholds are tuned for daily US-equity bars; override via the
    constructor for crypto / FX.
    """

    def __init__(
        self,
        momentum_window: int = 60,
        vol_window: int = 20,
        momentum_threshold: float = 0.02,
        vol_threshold: float = 0.30,
    ) -> None:
        self.momentum_window = int(momentum_window)
        self.vol_window = int(vol_window)
        self.momentum_threshold = float(momentum_threshold)
        self.vol_threshold = float(vol_threshold)

    def classify(self, benchmark_prices: pd.Series | pd.DataFrame | list[float]) -> Regime:
        if isinstance(benchmark_prices, pd.DataFrame):
            if "close" in benchmark_prices.columns:
                series = benchmark_prices["close"]
            else:
                # First numeric column.
                num_cols = benchmark_prices.select_dtypes(include=[float, int]).columns
                if not len(num_cols):
                    return "neutral"
                series = benchmark_prices[num_cols[0]]
        elif isinstance(benchmark_prices, pd.Series):
            series = benchmark_prices
        else:
            series = pd.Series(list(benchmark_prices), dtype=float)
        series = pd.to_numeric(series, errors="coerce").dropna()
        if len(series) < self.momentum_window + 1:
            return "neutral"
        latest = float(series.iloc[-1])
        sma = float(series.tail(self.momentum_window).mean())
        momentum = (latest / sma) - 1.0 if sma > 0 else 0.0
        vol = float(
            series.pct_change().tail(self.vol_window).std() * np.sqrt(252.0)
        )
        if momentum > self.momentum_threshold and vol < self.vol_threshold:
            return "risk_on"
        if momentum < -self.momentum_threshold or vol > 1.5 * self.vol_threshold:
            return "risk_off"
        return "neutral"

    def classify_from_bars(
        self,
        bars: pd.DataFrame,
        benchmark_vt_symbol: str,
    ) -> Regime:
        if bars is None or bars.empty:
            return "neutral"
        sub = bars[bars["vt_symbol"] == benchmark_vt_symbol].sort_values("timestamp")
        if sub.empty:
            return "neutral"
        return self.classify(sub["close"])


__all__ = ["MarketRegimeClassifier", "Regime"]
