"""Tests for the MinVariance / Markowitz portfolio constructors."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from aqp.core.types import Direction, Signal, Symbol
from aqp.strategies.portfolio_opt.min_variance import (
    MarkowitzPortfolio,
    MinVariancePortfolio,
)


def _bars_panel(symbols: list[str], n_days: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    rows = []
    for sym in symbols:
        rets = rng.normal(0.0005, 0.012, size=n_days)
        prices = 100 * (1 + pd.Series(rets)).cumprod().values
        for i, ts in enumerate(dates):
            rows.append(
                {
                    "timestamp": ts,
                    "vt_symbol": sym,
                    "open": float(prices[i]),
                    "high": float(prices[i] * 1.01),
                    "low": float(prices[i] * 0.99),
                    "close": float(prices[i]),
                    "volume": 1_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def _signals(symbols: list[str]) -> list[Signal]:
    return [
        Signal(
            symbol=Symbol.parse(s),
            strength=0.5,
            direction=Direction.LONG,
            timestamp=datetime(2024, 1, 1),
            confidence=0.6,
            horizon_days=21,
            source="test",
        )
        for s in symbols
    ]


def test_min_variance_weights_sum_to_one() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE"]
    bars = _bars_panel(syms)
    portfolio = MinVariancePortfolio(lookback_periods=120, max_weight=0.6)
    targets = portfolio.construct(_signals(syms), {"history": bars})
    assert targets, "expected non-empty targets"
    total = sum(t.target_weight for t in targets)
    assert pytest.approx(total, rel=1e-2) == 1.0
    for t in targets:
        assert t.target_weight <= 0.6 + 1e-9


def test_min_variance_falls_back_to_equal_when_history_empty() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE"]
    portfolio = MinVariancePortfolio(lookback_periods=120)
    targets = portfolio.construct(_signals(syms), {"history": pd.DataFrame()})
    assert targets, "expected fallback equal weights"
    weights = [t.target_weight for t in targets]
    # Equal weight when no history.
    assert pytest.approx(weights[0], abs=1e-6) == weights[1]


def test_markowitz_weights_sum_to_one() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE"]
    bars = _bars_panel(syms)
    portfolio = MarkowitzPortfolio(
        lookback_periods=120, risk_aversion=2.0, max_weight=0.6
    )
    targets = portfolio.construct(_signals(syms), {"history": bars})
    assert targets, "expected non-empty targets"
    total = sum(t.target_weight for t in targets)
    assert 0.85 <= total <= 1.05  # Optimiser tolerance.


def test_min_variance_long_only_no_negative_weights() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE"]
    bars = _bars_panel(syms)
    portfolio = MinVariancePortfolio(lookback_periods=120, long_only=True)
    targets = portfolio.construct(_signals(syms), {"history": bars})
    for t in targets:
        assert t.target_weight >= 0.0
