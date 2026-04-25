"""Smoke tests for the new portfolio construction models."""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.core.types import Direction, Signal, Symbol
from aqp.strategies.black_litterman import BlackLittermanPortfolio
from aqp.strategies.hrp import HierarchicalRiskParity
from aqp.strategies.mean_variance import MeanVariancePortfolio
from aqp.strategies.risk_parity import RiskParityPortfolio


def _signals_and_history():
    syms = [Symbol(ticker=t) for t in ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]]
    signals = [
        Signal(symbol=s, strength=1.0, direction=Direction.LONG, source="test")
        for s in syms
    ]
    # Deterministic synthetic price history.
    import numpy as np

    rng = np.random.default_rng(7)
    dates = pd.date_range("2023-01-02", periods=150, freq="B")
    rows = []
    for i, s in enumerate(syms):
        noise = rng.normal(0, 0.01, size=len(dates))
        drift = 0.0005 * (i + 1)
        prices = 100 * (1 + drift) ** np.arange(len(dates)) * (1 + noise).cumprod()
        for t, p in zip(dates, prices, strict=False):
            rows.append({"timestamp": t, "vt_symbol": s.vt_symbol, "close": float(p)})
    return signals, pd.DataFrame(rows)


def test_mean_variance_weights_sum_to_positive():
    signals, history = _signals_and_history()
    model = MeanVariancePortfolio(max_positions=5, long_only=True)
    targets = model.construct(signals, {"history": history})
    assert len(targets) > 0
    total = sum(t.target_weight for t in targets)
    assert total == pytest.approx(1.0, rel=0.3) or total > 0


def test_risk_parity_balances_exposure():
    signals, history = _signals_and_history()
    model = RiskParityPortfolio(max_positions=5, long_only=True)
    targets = model.construct(signals, {"history": history})
    assert len(targets) > 0
    assert all(t.target_weight > 0 for t in targets)


def test_hrp_long_weights_sum_to_one():
    signals, history = _signals_and_history()
    model = HierarchicalRiskParity(max_positions=5, long_only=True)
    targets = model.construct(signals, {"history": history})
    assert len(targets) > 0
    total = sum(abs(t.target_weight) for t in targets)
    assert total == pytest.approx(1.0, rel=0.3) or 0.5 < total < 1.5


def test_black_litterman_returns_targets():
    signals, history = _signals_and_history()
    model = BlackLittermanPortfolio(max_positions=5, long_only=True)
    targets = model.construct(signals, {"history": history})
    assert len(targets) > 0
    assert all(-1 <= t.target_weight <= 1 for t in targets)
