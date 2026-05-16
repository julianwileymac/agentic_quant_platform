"""Tests for :class:`VarianceSwapSynthetic`."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from aqp.core.types import Symbol
from aqp.strategies.options.variance_swap import (
    StripLeg,
    VarianceSwapSynthetic,
    replication_weights,
)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("VarianceSwapSynthetic") is VarianceSwapSynthetic


def test_replication_weights_split_around_forward() -> None:
    strikes = np.array([90, 95, 100, 105, 110], dtype=float)
    legs = replication_weights(forward=100.0, strikes=strikes)
    # Below F=100 → puts; above F → calls; at F → call by convention.
    by_strike = {l.strike: l for l in legs}
    assert by_strike[90].is_call is False
    assert by_strike[95].is_call is False
    assert by_strike[100].is_call is True
    assert by_strike[110].is_call is True
    # Weights monotonically decrease as 1/K^2 grows further out (no — actually
    # the K^2 in denominator grows as K grows, so weight DECREASES; for K=90 vs 95,
    # weight at K=90 should be larger). Confirm directional ordering.
    assert by_strike[90].weight > by_strike[110].weight


def test_invalid_side_raises() -> None:
    with pytest.raises(ValueError):
        VarianceSwapSynthetic(side="straddle")


def test_emits_strip_on_target_weekday() -> None:
    bars = pd.DataFrame(
        [
            {
                "vt_symbol": "SPY.NYSE",
                "timestamp": datetime(2024, 1, 1),  # Monday
                "close": 400.0,
            }
        ]
    )
    alpha = VarianceSwapSynthetic(
        underlying="SPY.NYSE", open_day_of_week=0, n_strikes=5, strike_width=10.0
    )
    signals = alpha.generate_signals(
        bars=bars, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    # 5 legs (one per strike).
    assert len(signals) == 5


def test_no_emit_off_weekday() -> None:
    bars = pd.DataFrame(
        [
            {
                "vt_symbol": "SPY.NYSE",
                "timestamp": datetime(2024, 1, 2),  # Tuesday
                "close": 400.0,
            }
        ]
    )
    alpha = VarianceSwapSynthetic(underlying="SPY.NYSE", open_day_of_week=0)
    signals = alpha.generate_signals(
        bars=bars, universe=[Symbol.parse("SPY.NYSE")], context={}
    )
    assert signals == []


_ = StripLeg  # keep import alive for IDEs
