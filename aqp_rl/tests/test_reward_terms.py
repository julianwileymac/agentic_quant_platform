"""Reward-term primitives + composite decomposition."""
from __future__ import annotations

import pytest

from aqp_rl.core.reward import CompositeReward
from aqp_rl.rewards.cost import TurnoverPenaltyTerm
from aqp_rl.rewards.pnl import LogReturnTerm, PnLTerm
from aqp_rl.rewards.risk import DrawdownPenaltyTerm, SharpeTerm, SortinoTerm


def test_pnl_term_basic():
    term = PnLTerm(weight=1.0, scale=1.0)
    delta = term.compute({"portfolio_value": 100}, None, {"portfolio_value": 110}, {})
    assert delta == pytest.approx(10.0)


def test_log_return_term_zero_when_undefined():
    term = LogReturnTerm()
    assert term.compute({"portfolio_value": 0.0}, None, {"portfolio_value": 100.0}, {}) == 0.0


def test_drawdown_penalty_uses_info_drawdown():
    term = DrawdownPenaltyTerm(weight=0.5)
    contribution = term.compute({}, None, {}, {"drawdown": -0.1})
    assert contribution < 0


def test_turnover_penalty_negative():
    term = TurnoverPenaltyTerm(weight=1.0, cost_pct=0.001)
    out = term.compute({}, None, {}, {"turnover": 0.5})
    assert out == pytest.approx(-0.0005)


def test_composite_reward_decomposition():
    reward = CompositeReward(
        terms=[
            PnLTerm(weight=1.0, scale=1.0),
            DrawdownPenaltyTerm(weight=1.0),
        ]
    )
    info: dict = {}
    total = reward.compute(
        {"portfolio_value": 100},
        None,
        {"portfolio_value": 110},
        info,
    )
    info["drawdown"] = -0.05
    decomposition = reward.decomposition(
        {"portfolio_value": 100}, None, {"portfolio_value": 110}, info
    )
    assert isinstance(decomposition, dict)
    assert "pnl" in decomposition
    assert total > 0


def test_sharpe_term_warmup():
    term = SharpeTerm(min_steps=10)
    for i in range(5):
        out = term.compute({"portfolio_value": 100 + i}, None, {"portfolio_value": 100 + i + 1}, {})
        assert out == 0.0  # below min_steps → no Sharpe yet
    # Push past the warm-up — Sharpe should now be finite.
    for i in range(5, 12):
        out = term.compute({"portfolio_value": 100 + i}, None, {"portfolio_value": 100 + i + 1}, {})
    assert isinstance(out, float)


def test_sortino_term_zero_when_no_downside():
    term = SortinoTerm(min_steps=2)
    for _ in range(3):
        term.compute({"portfolio_value": 100}, None, {"portfolio_value": 110}, {})
    out = term.compute({"portfolio_value": 110}, None, {"portfolio_value": 120}, {})
    assert out == 0.0
