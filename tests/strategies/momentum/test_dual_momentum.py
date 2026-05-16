"""Tests for :class:`DualMomentumAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.momentum.dual_momentum import DualMomentumAlpha


def _bars(prices: dict[str, np.ndarray], start: datetime) -> pd.DataFrame:
    rows = []
    for sym, close in prices.items():
        for i, px in enumerate(close):
            rows.append(
                {
                    "vt_symbol": sym,
                    "timestamp": start + timedelta(days=i),
                    "close": float(px),
                }
            )
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("DualMomentumAlpha") is DualMomentumAlpha


def test_picks_best_when_beats_cash() -> None:
    n = 260
    start = datetime(2023, 1, 1)
    bars = _bars(
        {
            "QQQ.NASDAQ": np.linspace(100.0, 150.0, n),
            "TLT.NASDAQ": np.linspace(100.0, 90.0, n),
        },
        start,
    )
    alpha = DualMomentumAlpha(formation_period=126, cash_proxy="TLT.NASDAQ")
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("QQQ.NASDAQ")],
        context={"current_time": start + timedelta(days=n - 1)},
    )
    assert len(signals) == 1
    assert signals[0].symbol.ticker == "QQQ"
    assert signals[0].direction is Direction.LONG


def test_falls_back_to_cash_when_best_loses_to_cash() -> None:
    n = 260
    start = datetime(2023, 1, 1)
    bars = _bars(
        {
            "QQQ.NASDAQ": np.linspace(150.0, 100.0, n),  # losing
            "TLT.NASDAQ": np.linspace(100.0, 110.0, n),  # winning
        },
        start,
    )
    alpha = DualMomentumAlpha(formation_period=126, cash_proxy="TLT.NASDAQ")
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("QQQ.NASDAQ")],
        context={"current_time": start + timedelta(days=n - 1)},
    )
    assert len(signals) == 1
    assert signals[0].symbol.ticker == "TLT"
    assert "safe haven" in (signals[0].rationale or "")
