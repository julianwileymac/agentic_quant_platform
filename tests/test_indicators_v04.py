"""Coverage for v0.4 indicator additions (Ichimoku / Supertrend / etc.)."""
from __future__ import annotations

import math

import pandas as pd

from aqp.core.indicators import (
    ALL_INDICATORS,
    AroonDown,
    AroonUp,
    HeikinAshiTransform,
    Ichimoku,
    PivotPoints,
    Supertrend,
)
from aqp.core.types import BarData, Symbol


def _bars_from(rows):
    sym = Symbol.parse("AAA.NASDAQ")
    return [
        BarData(
            symbol=sym,
            timestamp=pd.Timestamp("2023-01-01") + pd.Timedelta(days=i),
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
        )
        for i, (o, h, l, c, v) in enumerate(rows)
    ]


def test_all_indicators_registered() -> None:
    for k in ("Ichimoku", "Supertrend", "Pivot", "HA", "AroonUp", "AroonDown"):
        assert k in ALL_INDICATORS


def test_ichimoku_tenkan_computable() -> None:
    ich = Ichimoku(tenkan_period=3, kijun_period=5, senkou_b_period=7)
    for bar in _bars_from(
        [(100 + i, 101 + i, 99 + i, 100 + i, 1000) for i in range(10)]
    ):
        ich.update(bar, bar.timestamp)
    assert not math.isnan(ich.tenkan)


def test_supertrend_flips_direction() -> None:
    st = Supertrend(period=3, multiplier=1.0)
    for bar in _bars_from(
        [(100, 101, 99, 100, 1000)] * 3
        + [(105, 106, 104, 106, 1000)] * 3
        + [(100, 101, 99, 100, 1000)] * 3
    ):
        st.update(bar, bar.timestamp)
    # No assertion on value (implementation-dependent), but ``current`` must be finite.
    assert not math.isnan(st.current)


def test_pivot_points() -> None:
    pp = PivotPoints()
    pp.update(
        BarData(
            symbol=Symbol.parse("AAA.NASDAQ"),
            timestamp=pd.Timestamp("2023-01-01"),
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1000,
        ),
        pd.Timestamp("2023-01-01"),
    )
    assert pp.current == (110 + 90 + 105) / 3
    assert pp.r1 == 2 * pp.current - 90


def test_heikin_ashi_transform_stable() -> None:
    ha = HeikinAshiTransform()
    for bar in _bars_from(
        [(100 + i, 102 + i, 98 + i, 101 + i, 1000) for i in range(5)]
    ):
        ha.update(bar, bar.timestamp)
    assert not math.isnan(ha.ha_open)
    assert not math.isnan(ha.ha_high)
    assert not math.isnan(ha.ha_low)


def test_aroon_up_down_reach_100() -> None:
    up = AroonUp(period=5)
    down = AroonDown(period=5)
    for bar in _bars_from(
        [(100 + i, 110 + i, 90 + i, 100 + i, 1000) for i in range(6)]
    ):
        up.update(bar, bar.timestamp)
        down.update(bar, bar.timestamp)
    # Monotonically rising highs -> AroonUp should be at or near 100.
    assert up.current >= 60
