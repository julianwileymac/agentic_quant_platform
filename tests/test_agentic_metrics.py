"""Tests for the agentic-metrics module."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from aqp.backtest.agentic_metrics import evaluate, forward_return


def _bars(vt_symbol: str, start: datetime, days: int, prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": start + timedelta(days=i),
                "vt_symbol": vt_symbol,
                "close": p,
            }
            for i, p in enumerate(prices)
        ]
    )


def test_forward_return_happy_path() -> None:
    start = datetime(2024, 3, 1)
    bars = _bars("AAPL.NASDAQ", start, 5, [100, 101, 102, 103, 104])
    fret = forward_return(bars, "AAPL.NASDAQ", start, horizon_days=3)
    # (103 - 100) / 100 == 0.03
    assert abs(fret - 0.03) < 1e-9


def test_evaluate_hit_rate_positive_signal_up_market() -> None:
    start = datetime(2024, 3, 1)
    bars = _bars("AAPL.NASDAQ", start, 5, [100, 101, 102, 103, 104])
    decisions = [
        {
            "vt_symbol": "AAPL.NASDAQ",
            "ts": start,
            "action": "BUY",
            "size_pct": 0.2,
            "confidence": 0.8,
            "rating": "buy",
            "token_cost_usd": 0.01,
        },
    ]
    metrics = evaluate(decisions, bars, horizon_days=3)
    assert metrics.n_decisions == 1
    assert metrics.hit_rate == 1.0
    assert metrics.total_cost_usd == 0.01


def test_evaluate_empty_returns_zeros() -> None:
    m = evaluate([], pd.DataFrame(), horizon_days=5)
    assert m.n_decisions == 0
    assert m.hit_rate == 0.0
