"""Tests for the built-in incremental indicators."""
from __future__ import annotations

import math

import pytest

from aqp.core.indicators import (
    ALL_INDICATORS,
    AverageTrueRange,
    BollingerBands,
    ExponentialMovingAverage,
    MovingAverageConvergenceDivergence,
    RelativeStrengthIndex,
    RollingWindow,
    SimpleMovingAverage,
    build_indicator,
    warmup,
)
from aqp.core.types import BarData, Symbol


def _make_bar(t: int, close: float = 100.0, volume: float = 1_000.0) -> BarData:
    from datetime import datetime, timedelta

    return BarData(
        symbol=Symbol(ticker="TEST"),
        timestamp=datetime(2026, 1, 1) + timedelta(days=t),
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=volume,
    )


def test_rolling_window_basic():
    w = RollingWindow[int](3)
    assert not w.is_ready
    w.add(1)
    w.add(2)
    w.add(3)
    assert w.is_ready
    # Most recent first.
    assert w[0] == 3 and w[2] == 1
    w.add(4)
    assert w[0] == 4 and w[2] == 2


def test_sma_converges_to_arithmetic_mean():
    sma = SimpleMovingAverage(5)
    values = [1, 2, 3, 4, 5]
    for v in values:
        sma.update(v)
    assert sma.is_ready
    assert sma.current == pytest.approx(3.0)


def test_ema_respects_alpha():
    ema = ExponentialMovingAverage(10)
    warmup(ema, [100] * 10)
    for _ in range(20):
        ema.update(100)
    assert ema.current == pytest.approx(100.0)


def test_rsi_bounded():
    rsi = RelativeStrengthIndex(14)
    # Monotonically increasing → RSI ≈ 100
    for i in range(30):
        rsi.update(100 + i)
    assert 90 <= rsi.current <= 100


def test_macd_signal_and_histogram():
    macd = MovingAverageConvergenceDivergence(fast=3, slow=6, signal=3)
    vals = list(range(1, 60))
    for v in vals:
        macd.update(float(v))
    assert not math.isnan(macd.current)
    assert not math.isnan(macd.signal_value)


def test_bollinger_bands_order():
    bb = BollingerBands(period=10, k=2.0)
    for v in range(100, 120):
        bb.update(float(v))
    assert bb.upper > bb.middle > bb.lower


def test_atr_nonnegative():
    atr = AverageTrueRange(period=5)
    for t in range(20):
        atr.update(_make_bar(t, close=100 + t))
    assert atr.current >= 0


def test_registry_size_and_build():
    # Expect at least 25 indicators in the registry.
    assert len(ALL_INDICATORS) >= 25
    ind = build_indicator("SMA", period=5)
    assert isinstance(ind, SimpleMovingAverage)
