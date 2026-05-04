"""Signal builder tests — no vbt-pro required.

These check the panel-builder logic without invoking vbt-pro itself.
"""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.backtest.vbtpro.data_utils import (
    OHLCVPanel,
    pivot_close,
    pivot_ohlcv,
    universe_from_bars,
)
from aqp.backtest.vbtpro.signal_builder import SignalArrays, build_signal_arrays
from aqp.core.interfaces import IAlphaModel
from aqp.core.types import Direction, Signal, Symbol


class _ConstantLongAlpha(IAlphaModel):
    """Always emits LONG for the most recent bar of every symbol."""

    def generate_signals(self, bars, universe, context):
        ts = context.get("current_time")
        out = []
        for sym in universe:
            out.append(
                Signal(
                    symbol=sym,
                    strength=0.5,
                    direction=Direction.LONG,
                    timestamp=ts,
                    confidence=0.9,
                    horizon_days=5,
                    source="test",
                )
            )
        return out


def test_pivot_close_round_trip(synthetic_bars: pd.DataFrame) -> None:
    close = pivot_close(synthetic_bars)
    assert close.shape[1] == 5
    assert close.index.is_monotonic_increasing
    assert close.isna().sum().sum() == 0


def test_pivot_ohlcv_returns_aligned_panel(synthetic_bars: pd.DataFrame) -> None:
    ohlcv = pivot_ohlcv(synthetic_bars)
    assert isinstance(ohlcv, OHLCVPanel)
    assert ohlcv.open.shape == ohlcv.close.shape
    assert ohlcv.high.shape == ohlcv.low.shape
    assert list(ohlcv.columns) == sorted(synthetic_bars["vt_symbol"].unique())


def test_universe_from_bars(synthetic_bars: pd.DataFrame) -> None:
    universe = universe_from_bars(synthetic_bars)
    assert len(universe) == 5
    assert all(isinstance(s, Symbol) for s in universe)


def test_build_signal_arrays_per_bar_loop(synthetic_bars: pd.DataFrame) -> None:
    close = pivot_close(synthetic_bars)
    arr = build_signal_arrays(
        _ConstantLongAlpha(),
        bars=synthetic_bars,
        close=close,
        warmup_bars=5,
        record_signals=True,
    )
    assert isinstance(arr, SignalArrays)
    # Each symbol should have entries True on the warmup+1 bar.
    assert arr.entries.iloc[5].any()
    assert arr.entries.iloc[5].sum() == 5
    # No re-entries — once long, future bars stay False until an exit.
    assert arr.entries.iloc[6].sum() == 0
    assert len(arr.signal_records) > 0


def test_build_signal_arrays_uses_panel_path() -> None:
    """When the alpha implements ``generate_panel_signals`` we use it."""
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5),
            "vt_symbol": ["AAPL.NASDAQ"] * 5,
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1e6] * 5,
        }
    )

    class _PanelAlpha:
        def generate_panel_signals(self, bars, universe, context):
            close = context["close"]
            entries = pd.DataFrame(False, index=close.index, columns=close.columns)
            entries.iloc[1, 0] = True
            exits = pd.DataFrame(False, index=close.index, columns=close.columns)
            exits.iloc[3, 0] = True
            return SignalArrays(entries=entries, exits=exits)

    close = pivot_close(bars)
    arr = build_signal_arrays(_PanelAlpha(), bars=bars, close=close, warmup_bars=0)
    assert arr.entries.iloc[1, 0] is True or arr.entries.iloc[1, 0] == True  # noqa: E712
    assert arr.exits.iloc[3, 0] is True or arr.exits.iloc[3, 0] == True  # noqa: E712
