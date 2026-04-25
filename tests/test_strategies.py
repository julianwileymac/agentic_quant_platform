"""Smoke tests for the Lean-style 5-stage framework."""
from __future__ import annotations

import pandas as pd

from aqp.core.types import Direction, Signal, Symbol
from aqp.strategies.momentum import MomentumAlpha
from aqp.strategies.portfolio import EqualWeightPortfolio, SignalWeightedPortfolio
from aqp.strategies.risk_models import BasicRiskModel
from aqp.strategies.universes import StaticUniverse


def test_static_universe():
    uni = StaticUniverse(symbols=["AAPL", "MSFT"])
    syms = uni.select(None, {})
    assert {s.ticker for s in syms} == {"AAPL", "MSFT"}


def test_momentum_emits_signals(synthetic_bars: pd.DataFrame) -> None:
    alpha = MomentumAlpha(lookback=30, top_quantile=0.3, allow_short=False)
    universe = [Symbol.parse(v) for v in synthetic_bars["vt_symbol"].unique()]
    signals = alpha.generate_signals(synthetic_bars, universe, {})
    assert isinstance(signals, list)


def test_equal_weight_portfolio_normalises():
    sig = [
        Signal(symbol=Symbol(ticker="AAA"), strength=0.8, direction=Direction.LONG),
        Signal(symbol=Symbol(ticker="BBB"), strength=0.6, direction=Direction.LONG),
    ]
    p = EqualWeightPortfolio(max_positions=2)
    targets = p.construct(sig, {})
    assert abs(sum(abs(t.target_weight) for t in targets) - 1.0) < 1e-9


def test_basic_risk_caps_positions():
    from aqp.core.types import PortfolioTarget

    targets = [
        PortfolioTarget(symbol=Symbol(ticker="AAA"), target_weight=0.6),
        PortfolioTarget(symbol=Symbol(ticker="BBB"), target_weight=0.6),
    ]
    r = BasicRiskModel(max_position_pct=0.3)
    out = r.evaluate(targets, {"drawdown": 0.0})
    assert max(abs(t.target_weight) for t in out) <= 0.3 + 1e-9


def test_signal_weighted_portfolio():
    sig = [
        Signal(symbol=Symbol(ticker="AAA"), strength=1.0, direction=Direction.LONG),
        Signal(symbol=Symbol(ticker="BBB"), strength=0.5, direction=Direction.LONG),
    ]
    p = SignalWeightedPortfolio(max_positions=2, long_only=True)
    targets = p.construct(sig, {})
    assert len(targets) == 2
    assert targets[0].target_weight > targets[1].target_weight
