"""Tests for :class:`VRPDeltaHedgedStraddle`."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.options.vrp_straddle import OptionLeg, VRPDeltaHedgedStraddle


def _bars(symbol: str, n: int, start: datetime, price: float = 400.0) -> pd.DataFrame:
    rows = [
        {
            "vt_symbol": symbol,
            "timestamp": start + timedelta(days=i),
            "close": price,
        }
        for i in range(n)
    ]
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("VRPDeltaHedgedStraddle") is VRPDeltaHedgedStraddle


def test_open_signals_on_target_weekday() -> None:
    # 2024-01-01 is a Monday → open_day_of_week=0 matches.
    bars = _bars("SPY.NYSE", n=5, start=datetime(2024, 1, 1))
    alpha = VRPDeltaHedgedStraddle(underlying="SPY.NYSE", open_day_of_week=0)
    signals = alpha.generate_signals(
        bars=bars, universe=[Symbol.parse("SPY.NYSE")], context={"current_time": None}
    )
    # On Friday (day 4 = 2024-01-05) — not the target — must NOT open.
    # Run with bars stopping at Monday only:
    monday_only = bars.iloc[:1]
    sig = alpha.generate_signals(
        bars=monday_only, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    assert len(sig) == 2
    # All open signals are SHORT.
    assert all(s.direction is Direction.SHORT for s in sig)


def test_no_open_signals_off_weekday() -> None:
    bars = _bars("SPY.NYSE", n=1, start=datetime(2024, 1, 2))  # Tuesday
    alpha = VRPDeltaHedgedStraddle(underlying="SPY.NYSE", open_day_of_week=0)
    sig = alpha.generate_signals(
        bars=bars, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    assert sig == []


def test_delta_hedge_fires_when_net_delta_above_tolerance() -> None:
    bars = _bars("SPY.NYSE", n=1, start=datetime(2024, 1, 2))  # off weekday
    alpha = VRPDeltaHedgedStraddle(
        underlying="SPY.NYSE", open_day_of_week=0, delta_tolerance=0.1
    )
    portfolio = [
        OptionLeg(strike=400.0, dte_days=7, is_call=True, quantity=-1.0, delta=0.5),
        OptionLeg(strike=400.0, dte_days=7, is_call=False, quantity=-1.0, delta=-0.4),
    ]
    sig = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("SPY.NYSE")],
        context={"portfolio": portfolio},
    )
    # Net delta = -1*0.5 + -1*(-0.4) = -0.1 → at boundary, but
    # tolerance is strictly < 0.1 to fire so we use a clearer case:
    portfolio2 = [
        OptionLeg(strike=400.0, dte_days=7, is_call=True, quantity=-1.0, delta=0.5),
        OptionLeg(strike=400.0, dte_days=7, is_call=False, quantity=-1.0, delta=-0.1),
    ]
    sig2 = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("SPY.NYSE")],
        context={"portfolio": portfolio2},
    )
    # Net delta = -1*0.5 + -1*(-0.1) = -0.4 → fire LONG hedge.
    hedges = [s for s in sig2 if "delta hedge" in (s.rationale or "")]
    assert len(hedges) == 1
    assert hedges[0].direction is Direction.LONG


def test_delta_hedge_skips_when_below_tolerance() -> None:
    bars = _bars("SPY.NYSE", n=1, start=datetime(2024, 1, 2))
    alpha = VRPDeltaHedgedStraddle(
        underlying="SPY.NYSE", open_day_of_week=0, delta_tolerance=0.5
    )
    portfolio = [
        OptionLeg(strike=400.0, dte_days=7, is_call=True, quantity=-1.0, delta=0.5),
        OptionLeg(strike=400.0, dte_days=7, is_call=False, quantity=-1.0, delta=-0.4),
    ]
    sig = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("SPY.NYSE")],
        context={"portfolio": portfolio},
    )
    assert sig == []
