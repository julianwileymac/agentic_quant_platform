"""Implementation Shortfall reward — unit tests."""
from __future__ import annotations

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.implementation_shortfall import ImplementationShortfall


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "implementation_shortfall" in registry
    assert registry["implementation_shortfall"] is ImplementationShortfall


def test_zero_execution_yields_zero_reward():
    term = ImplementationShortfall()
    out = term.compute(state={}, action=None, next_state={}, info={"executed_shares": 0})
    assert out == 0.0


def test_arrival_eq_fill_yields_zero_reward():
    """Fill matches arrival exactly ⇒ no shortfall."""
    term = ImplementationShortfall()
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "executed_shares": 100,
            "arrival_price": 50.0,
            "fill_price": 50.0,
            "total_shares": 1000,
        },
    )
    assert out == 0.0


def test_fill_below_arrival_negative_reward():
    """Selling cheaper than arrival ⇒ positive shortfall ⇒ negative reward."""
    term = ImplementationShortfall()
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "executed_shares": 100,
            "arrival_price": 50.0,
            "fill_price": 49.0,
            "total_shares": 1000,
        },
    )
    # is_step = 100 * (50 - 49) = 100; reward = -(100 + 0) / 1000 = -0.1
    assert out == pytest.approx(-0.1)


def test_fill_above_arrival_positive_reward():
    """Hitting a higher bid than arrival ⇒ negative shortfall ⇒ positive reward."""
    term = ImplementationShortfall()
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "executed_shares": 100,
            "arrival_price": 50.0,
            "fill_price": 51.0,
            "total_shares": 1000,
        },
    )
    assert out == pytest.approx(0.1)


def test_lambda_risk_penalises_variance():
    """Adding fill-price variance with λ > 0 makes the reward more negative."""
    term_no_risk = ImplementationShortfall(lambda_risk=0.0)
    term_with_risk = ImplementationShortfall(lambda_risk=10.0)
    info = {
        "executed_shares": 100,
        "arrival_price": 50.0,
        "fill_price": 49.0,
        "total_shares": 1000,
        "fill_price_variance": 0.05,
    }
    out_no_risk = term_no_risk.compute(state={}, action=None, next_state={}, info=info)
    out_with_risk = term_with_risk.compute(state={}, action=None, next_state={}, info=info)
    assert out_with_risk < out_no_risk


def test_missing_total_shares_falls_back_to_unnormalised():
    """Without ``total_shares`` the term emits the raw shortfall."""
    term = ImplementationShortfall()
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "executed_shares": 100,
            "arrival_price": 50.0,
            "fill_price": 49.0,
        },
    )
    # is_step = 100; reward = -(100 + 0) / 1 = -100
    assert out == pytest.approx(-100.0)


def test_negative_lambda_raises():
    with pytest.raises(ValueError):
        ImplementationShortfall(lambda_risk=-1.0)
