"""Tests for :class:`SVMFXTrendAlpha`. Skipped when sklearn missing."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from aqp.core.types import Symbol  # noqa: E402
from aqp.strategies.ml.svm_fx_trend import SVMFXTrendAlpha  # noqa: E402


def _bars(n: int, drift: float, noise: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 1.10 + np.cumsum(np.full(n, drift) + rng.normal(0.0, noise, size=n))
    rows = [
        {
            "vt_symbol": "EURUSD.FX",
            "timestamp": datetime(2024, 1, 1) + timedelta(days=i),
            "close": float(close[i]),
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("SVMFXTrendAlpha") is SVMFXTrendAlpha


def test_no_signal_when_insufficient_history() -> None:
    bars = _bars(n=20, drift=0.0001, noise=0.001)
    alpha = SVMFXTrendAlpha(train_window=200)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("EURUSD.FX")],
        context={"current_time": datetime(2024, 1, 21)},
    )
    assert signals == []


def test_trains_and_emits_on_sufficient_history() -> None:
    bars = _bars(n=400, drift=0.0005, noise=0.001, seed=11)
    alpha = SVMFXTrendAlpha(train_window=200, margin_threshold=0.0)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("EURUSD.FX")],
        context={"current_time": bars.iloc[-1]["timestamp"]},
    )
    # Strong upward drift → expect a long signal of some strength.
    assert signals
