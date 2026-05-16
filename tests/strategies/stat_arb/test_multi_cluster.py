"""Tests for :class:`MultiClusterMeanReversionAlpha`."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.stat_arb.multi_cluster import MultiClusterMeanReversionAlpha


def _bars(symbols: dict[str, list[float]], start: datetime) -> pd.DataFrame:
    rows = []
    for sym, prices in symbols.items():
        for i, px in enumerate(prices):
            rows.append(
                {
                    "vt_symbol": f"{sym}.NASDAQ",
                    "timestamp": start + timedelta(days=i),
                    "close": float(px),
                }
            )
    return pd.DataFrame(rows)


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("MultiClusterMeanReversionAlpha") is MultiClusterMeanReversionAlpha


def test_residual_drives_short_for_outperformers() -> None:
    # Two stocks in the same "tech" cluster: AAPL +20%, MSFT flat.
    bars = _bars(
        {
            "AAPL": [100.0, 105.0, 110.0, 115.0, 120.0],
            "MSFT": [200.0, 200.0, 200.0, 200.0, 200.0],
        },
        datetime(2024, 1, 1),
    )
    alpha = MultiClusterMeanReversionAlpha(
        lookback=2,
        clusters={"AAPL": "tech", "MSFT": "tech"},
        z_threshold=0.1,
    )
    universe = [Symbol.parse("AAPL.NASDAQ"), Symbol.parse("MSFT.NASDAQ")]
    signals = alpha.generate_signals(
        bars=bars, universe=universe, context={"current_time": datetime(2024, 1, 5)}
    )
    # AAPL is the outperformer in the cluster → expect SHORT.
    aapl = next((s for s in signals if s.symbol.ticker == "AAPL"), None)
    msft = next((s for s in signals if s.symbol.ticker == "MSFT"), None)
    assert aapl is not None
    assert aapl.direction is Direction.SHORT
    assert msft is not None
    assert msft.direction is Direction.LONG


def test_dollar_neutrality_weights_sum_to_one() -> None:
    bars = _bars(
        {
            "A": [100.0, 110.0, 120.0, 130.0],
            "B": [200.0, 198.0, 196.0, 194.0],
            "C": [50.0, 50.5, 51.0, 51.5],
        },
        datetime(2024, 1, 1),
    )
    alpha = MultiClusterMeanReversionAlpha(lookback=2, z_threshold=0.0)
    universe = [
        Symbol.parse("A.NASDAQ"),
        Symbol.parse("B.NASDAQ"),
        Symbol.parse("C.NASDAQ"),
    ]
    signals = alpha.generate_signals(
        bars=bars, universe=universe, context={"current_time": datetime(2024, 1, 4)}
    )
    total_abs = sum(abs(s.strength) for s in signals)
    assert total_abs <= 1.0 + 1e-9
    assert total_abs > 0.0


def test_empty_bars_returns_empty() -> None:
    alpha = MultiClusterMeanReversionAlpha()
    signals = alpha.generate_signals(
        bars=pd.DataFrame(),
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={"current_time": datetime(2024, 1, 1)},
    )
    assert signals == []


def test_below_threshold_no_signals() -> None:
    # All stocks return ~identically → residuals near zero, z-score
    # under threshold.
    bars = _bars(
        {
            "A": [100.0, 100.01, 100.02, 100.03],
            "B": [100.0, 100.01, 100.02, 100.03],
        },
        datetime(2024, 1, 1),
    )
    alpha = MultiClusterMeanReversionAlpha(lookback=2, z_threshold=5.0)
    universe = [Symbol.parse("A.NASDAQ"), Symbol.parse("B.NASDAQ")]
    signals = alpha.generate_signals(
        bars=bars, universe=universe, context={"current_time": datetime(2024, 1, 4)}
    )
    assert signals == []
