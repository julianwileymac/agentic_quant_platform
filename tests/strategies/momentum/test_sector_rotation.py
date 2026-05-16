"""Tests for :class:`SectorMomentumRotationAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.momentum.sector_rotation import SectorMomentumRotationAlpha


def _trending_bars(
    symbols: dict[str, float], n: int = 260, start: datetime = datetime(2023, 1, 1)
) -> pd.DataFrame:
    """Build linearly-trending close series for the given symbols."""
    rows = []
    for sym, slope in symbols.items():
        close = 100.0 + slope * np.arange(n)
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

    assert resolve("SectorMomentumRotationAlpha") is SectorMomentumRotationAlpha


def test_top_decile_includes_strongest_only() -> None:
    bars = _trending_bars(
        {
            "XLK.NYSE": 0.5,  # strong
            "XLF.NYSE": 0.2,
            "XLV.NYSE": 0.1,
            "XLY.NYSE": -0.3,  # weakest
            "SPY.NYSE": 0.3,  # market proxy
        },
        n=260,
    )
    universe = [
        Symbol.parse("XLK.NYSE"),
        Symbol.parse("XLF.NYSE"),
        Symbol.parse("XLV.NYSE"),
        Symbol.parse("XLY.NYSE"),
    ]
    alpha = SectorMomentumRotationAlpha(
        formation_period=126,
        top_decile=0.25,  # 1 of 4
        market_proxy="SPY.NYSE",
        market_sma_window=50,
        hold_bars=21,
    )
    signals = alpha.generate_signals(
        bars=bars,
        universe=universe,
        context={"current_time": datetime(2023, 9, 1)},
    )
    assert len(signals) == 1
    assert signals[0].symbol.ticker == "XLK"
    assert signals[0].direction is Direction.LONG


def test_market_filter_blocks_when_below_sma() -> None:
    # Downtrending market — proxy below SMA → no signals.
    n = 260
    start = datetime(2023, 1, 1)
    proxy_close = np.linspace(150.0, 100.0, n)
    rows = [
        {
            "vt_symbol": "SPY.NYSE",
            "timestamp": start + timedelta(days=i),
            "close": float(proxy_close[i]),
        }
        for i in range(n)
    ]
    # And some sectors that have positive trailing return regardless.
    for sym, slope in {"XLK.NYSE": 0.5, "XLF.NYSE": 0.3}.items():
        close = 100.0 + slope * np.arange(n)
        for i, px in enumerate(close):
            rows.append(
                {
                    "vt_symbol": sym,
                    "timestamp": start + timedelta(days=i),
                    "close": float(px),
                }
            )
    bars = pd.DataFrame(rows)
    alpha = SectorMomentumRotationAlpha(
        formation_period=126,
        top_decile=0.5,
        market_proxy="SPY.NYSE",
        market_sma_window=50,
    )
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("XLK.NYSE"), Symbol.parse("XLF.NYSE")],
        context={"current_time": start + timedelta(days=n - 1)},
    )
    assert signals == []


def test_insufficient_history_returns_empty() -> None:
    bars = _trending_bars({"XLK.NYSE": 0.5, "SPY.NYSE": 0.3}, n=30)
    alpha = SectorMomentumRotationAlpha(
        formation_period=126, top_decile=0.5, market_proxy="SPY.NYSE", market_sma_window=20
    )
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("XLK.NYSE")],
        context={"current_time": datetime(2023, 2, 1)},
    )
    assert signals == []
