"""Qlib-style metric ports — risk_analysis + turnover_report + indicator_analysis."""
from __future__ import annotations

import pandas as pd

from aqp.backtest.metrics import indicator_analysis, risk_analysis, turnover_report


def test_risk_analysis_sum_mode() -> None:
    returns = pd.Series([0.001, -0.0005, 0.002, 0.0, -0.001])
    out = risk_analysis(returns, freq="day", mode="sum")
    assert {"mean", "std", "annualized_return", "information_ratio", "max_drawdown"} <= out.keys()


def test_risk_analysis_product_mode() -> None:
    returns = pd.Series([0.01, 0.02, -0.01, 0.005])
    out = risk_analysis(returns, freq="day", mode="product")
    assert out["annualized_return"] != 0.0


def test_risk_analysis_empty() -> None:
    out = risk_analysis(pd.Series(dtype=float))
    assert out["mean"] == 0.0
    assert out["information_ratio"] == 0.0


def test_turnover_report() -> None:
    trades = pd.DataFrame(
        {"quantity": [10, -5, 20], "price": [100.0, 101.0, 99.0]}
    )
    equity = pd.Series([10000.0, 10050.0])
    out = turnover_report(trades, equity)
    assert out["n_trades"] == 3
    assert out["turnover_gross"] > 0


def test_indicator_analysis() -> None:
    frame = pd.DataFrame(
        {"pa": [0.01, 0.015, 0.02, -0.005], "ffr": [0.8, 0.9, 0.7, 0.95]}
    )
    out = indicator_analysis(frame)
    assert "pa" in out and "ffr" in out
    for name in ("mean", "std", "t_stat", "n"):
        assert name in out["pa"]
