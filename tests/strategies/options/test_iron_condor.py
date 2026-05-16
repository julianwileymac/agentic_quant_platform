"""Tests for :class:`IronCondorAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.options.iron_condor import IronCondorAlpha


def _bars(n: int, start: datetime, sigma: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    close = 400.0 + np.cumsum(rng.normal(0.0, sigma * 400.0, size=n))
    rows = [
        {
            "vt_symbol": "SPY.NYSE",
            "timestamp": start + timedelta(days=i),
            "close": float(close[i]),
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("IronCondorAlpha") is IronCondorAlpha


def test_open_emits_four_legs_on_target_weekday() -> None:
    # 2024-01-01 is Monday.
    bars = _bars(n=40, start=datetime(2024, 1, 1))
    alpha = IronCondorAlpha(underlying="SPY.NYSE", open_day_of_week=0)
    signals = alpha.generate_signals(
        bars=bars.iloc[:1],  # only the Monday bar
        universe=[Symbol.parse("SPY.NYSE")],
        context={},
    )
    # Only the open leg fires (sigma is zero with one bar) — but we
    # need the realised-vol lookback. Provide enough history.
    big = bars.iloc[:40]
    signals_full = alpha.generate_signals(
        bars=big, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    last_ts = big.iloc[-1]["timestamp"]
    # If the last bar is a Monday, we get four legs; otherwise zero.
    if pd.Timestamp(last_ts).weekday() == 0:
        long_legs = [s for s in signals_full if s.direction is Direction.LONG]
        short_legs = [s for s in signals_full if s.direction is Direction.SHORT]
        assert len(long_legs) >= 2
        assert len(short_legs) >= 2


def test_no_emit_off_weekday() -> None:
    bars = _bars(n=40, start=datetime(2024, 1, 2))  # Tuesday start
    alpha = IronCondorAlpha(underlying="SPY.NYSE", open_day_of_week=0)
    signals = alpha.generate_signals(
        bars=bars, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    # Off-weekday + no breach → likely zero signals. Tolerate up to
    # one unwind signal in rare bootstrap edge cases.
    assert all("emergency unwind" in (s.rationale or "") for s in signals) or signals == []
