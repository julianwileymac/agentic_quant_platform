"""Tests for :class:`CrossSectionalResidualAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from aqp.core.types import Symbol
from aqp.strategies.stat_arb.cross_sectional_residual import (
    CrossSectionalResidualAlpha,
)


def _bars_with_factors(
    symbols: dict[str, list[float]], factors: dict[str, list[float]], start: datetime
) -> pd.DataFrame:
    rows = []
    n = len(next(iter(symbols.values())))
    for sym, prices in symbols.items():
        for i in range(n):
            row: dict = {
                "vt_symbol": f"{sym}.NASDAQ",
                "timestamp": start + timedelta(days=i),
                "close": float(prices[i]),
            }
            for fname, fvals in factors.items():
                row[fname] = float(fvals[i])
            rows.append(row)
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("CrossSectionalResidualAlpha") is CrossSectionalResidualAlpha


def test_returns_signals_when_factor_columns_missing_gracefully() -> None:
    # No factor columns present → strategy must not crash.
    bars = pd.DataFrame(
        {
            "vt_symbol": ["A.NASDAQ"] * 30 + ["B.NASDAQ"] * 30,
            "timestamp": list(pd.date_range("2024-01-01", periods=30, freq="D"))
            + list(pd.date_range("2024-01-01", periods=30, freq="D")),
            "close": np.r_[
                np.linspace(100.0, 110.0, 30),
                np.linspace(100.0, 95.0, 30),
            ].tolist(),
        }
    )
    alpha = CrossSectionalResidualAlpha(lookback=25, z_threshold=0.1)
    universe = [Symbol.parse("A.NASDAQ"), Symbol.parse("B.NASDAQ")]
    signals = alpha.generate_signals(
        bars=bars,
        universe=universe,
        context={"current_time": datetime(2024, 1, 30)},
    )
    # Two stocks moving opposite directions → at least one signal each
    # side after demeaning.
    assert len(signals) >= 1


def test_factor_neutralisation_uses_provided_columns() -> None:
    n = 40
    start = datetime(2024, 1, 1)
    market = np.linspace(0.0, 0.1, n)
    bars = _bars_with_factors(
        symbols={
            "A": (100.0 * np.cumprod(1.0 + 0.01 + 0.5 * np.diff(market, prepend=0))).tolist(),
            "B": (100.0 * np.cumprod(1.0 - 0.01 + 0.5 * np.diff(market, prepend=0))).tolist(),
        },
        factors={"mkt_excess": market.tolist()},
        start=start,
    )
    alpha = CrossSectionalResidualAlpha(
        lookback=30,
        factor_columns=("mkt_excess",),
        z_threshold=0.0,
    )
    universe = [Symbol.parse("A.NASDAQ"), Symbol.parse("B.NASDAQ")]
    signals = alpha.generate_signals(
        bars=bars, universe=universe, context={"current_time": start + timedelta(days=n - 1)}
    )
    # Both stocks share the market component but have opposite idiosyncratic
    # drift → residuals are non-trivial → signals emitted.
    assert signals
