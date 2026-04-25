"""Tests for the FinRL-Trading-style ML stock selection alpha."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from aqp.core.types import Symbol
from aqp.strategies.ml_selection import MLStockSelectionAlpha


def _bars_panel(symbols: list[str], n_days: int = 220) -> pd.DataFrame:
    rng = np.random.default_rng(13)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    rows = []
    for i, sym in enumerate(symbols):
        # Each symbol has a slightly different drift so the model has
        # something to learn.
        drift = 0.0002 * (i + 1)
        rets = rng.normal(drift, 0.012, size=n_days)
        prices = 100 * (1 + pd.Series(rets)).cumprod().values
        for j, ts in enumerate(dates):
            rows.append(
                {
                    "timestamp": ts,
                    "vt_symbol": sym,
                    "open": float(prices[j]),
                    "high": float(prices[j] * 1.01),
                    "low": float(prices[j] * 0.99),
                    "close": float(prices[j]),
                    "volume": 1_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def test_ml_selection_emits_signals_for_top_quantile() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE", "DDD.NYSE", "EEE.NYSE"]
    bars = _bars_panel(syms)
    alpha = MLStockSelectionAlpha(
        model_kind="random_forest",
        feature_specs=["SMA:10", "SMA:30", "RSI:14"],
        forward_horizon_days=10,
        top_quantile=0.6,
        weight_method="equal",
    )
    universe = [Symbol.parse(s) for s in syms]
    signals = alpha.generate_signals(
        bars,
        universe,
        {"current_time": datetime(2023, 12, 1)},
    )
    assert signals, "expected at least one signal from top-quantile selection"
    weights = sum(s.strength for s in signals)
    assert 0.85 <= weights <= 1.05


def test_ml_selection_min_variance_allocates() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE", "DDD.NYSE"]
    bars = _bars_panel(syms)
    alpha = MLStockSelectionAlpha(
        model_kind="random_forest",
        feature_specs=["SMA:5", "SMA:20", "RSI:14"],
        forward_horizon_days=10,
        top_quantile=0.5,
        weight_method="min_variance",
        lookback_periods=120,
    )
    signals = alpha.generate_signals(
        bars,
        [Symbol.parse(s) for s in syms],
        {"current_time": datetime(2023, 12, 1)},
    )
    assert signals
    for sig in signals:
        assert 0.0 <= sig.strength <= 1.0


def test_ml_selection_with_threshold_filters_out_negatives() -> None:
    syms = ["AAA.NYSE", "BBB.NYSE", "CCC.NYSE"]
    bars = _bars_panel(syms)
    alpha = MLStockSelectionAlpha(
        model_kind="ridge",
        feature_specs=["SMA:5"],
        top_quantile=0.99,  # only the very top
        min_pred_return=10.0,  # impossible threshold
        weight_method="equal",
    )
    signals = alpha.generate_signals(
        bars,
        [Symbol.parse(s) for s in syms],
        {"current_time": datetime(2023, 12, 1)},
    )
    assert signals == []
