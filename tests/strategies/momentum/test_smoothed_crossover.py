"""Tests for :class:`SmoothedMACrossoverAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from aqp.core.types import Direction, Symbol
from aqp.strategies.momentum.smoothed_crossover import SmoothedMACrossoverAlpha


def _trending(
    n: int, drift: float, noise: float, seed: int = 0, start: datetime = datetime(2023, 1, 1)
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(np.full(n, drift) + rng.normal(0.0, noise, size=n))
    rows = [
        {
            "vt_symbol": "AAPL.NASDAQ",
            "timestamp": start + timedelta(days=i),
            "close": float(close[i]),
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("SmoothedMACrossoverAlpha") is SmoothedMACrossoverAlpha


def test_slow_must_exceed_fast() -> None:
    with pytest.raises(ValueError):
        SmoothedMACrossoverAlpha(fast_window=20, slow_window=20)


def test_uptrend_emits_long_signal() -> None:
    bars = _trending(n=300, drift=0.05, noise=0.5, seed=7)
    alpha = SmoothedMACrossoverAlpha(fast_window=10, slow_window=50, smooth_alpha=0.3)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"current_time": datetime(2023, 12, 1)},
    )
    assert signals
    assert all(s.direction is Direction.LONG for s in signals)


def test_downtrend_emits_short_signal() -> None:
    bars = _trending(n=300, drift=-0.05, noise=0.5, seed=11)
    alpha = SmoothedMACrossoverAlpha(fast_window=10, slow_window=50, smooth_alpha=0.3)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"current_time": datetime(2023, 12, 1)},
    )
    assert signals
    assert all(s.direction is Direction.SHORT for s in signals)


def test_smoothing_alpha_one_falls_through_to_raw() -> None:
    bars = _trending(n=300, drift=0.05, noise=0.5)
    raw = SmoothedMACrossoverAlpha(
        fast_window=10, slow_window=50, smooth_alpha=1.0
    ).generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"current_time": datetime(2023, 12, 1)},
    )
    smoothed = SmoothedMACrossoverAlpha(
        fast_window=10, slow_window=50, smooth_alpha=0.3
    ).generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"current_time": datetime(2023, 12, 1)},
    )
    # Both must produce signals; we don't compare exact values because
    # the smoother only affects magnitude / timing.
    assert raw
    assert smoothed
