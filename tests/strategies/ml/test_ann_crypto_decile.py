"""Tests for :class:`ANNCryptoDecileAlpha`. Skipped when sklearn missing."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from aqp.core.types import Symbol  # noqa: E402
from aqp.strategies.ml.ann_crypto_decile import ANNCryptoDecileAlpha  # noqa: E402


def _bars(n: int, drift: float, noise: float, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 30000.0 + np.cumsum(
        np.full(n, drift * 30000.0) + rng.normal(0.0, noise * 30000.0, size=n)
    )
    rows = [
        {
            "vt_symbol": "BTC.PERP",
            "timestamp": datetime(2024, 1, 1) + timedelta(hours=i),
            "close": float(close[i]),
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("ANNCryptoDecileAlpha") is ANNCryptoDecileAlpha


def test_no_signal_when_insufficient_history() -> None:
    bars = _bars(n=30, drift=0.0001, noise=0.005)
    alpha = ANNCryptoDecileAlpha(train_window=400)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("BTC.PERP")],
        context={"current_time": bars.iloc[-1]["timestamp"]},
    )
    assert signals == []


def test_runs_without_crashing_on_full_history() -> None:
    bars = _bars(n=800, drift=0.001, noise=0.01, seed=7)
    alpha = ANNCryptoDecileAlpha(
        train_window=400, decile_threshold=0.05, hidden_layer_sizes=(8,)
    )
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("BTC.PERP")],
        context={"current_time": bars.iloc[-1]["timestamp"]},
    )
    # Whether the signal fires depends on the trained model's
    # probability mass; the test only asserts the strategy runs to
    # completion without raising.
    assert isinstance(signals, list)
