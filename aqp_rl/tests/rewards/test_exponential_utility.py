"""Exponential (CARA) utility reward — unit tests."""
from __future__ import annotations

import math

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.exponential_utility import ExponentialUtility


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "exp_utility" in registry
    assert registry["exp_utility"] is ExponentialUtility


def test_zero_pnl_returns_minus_one():
    """ΔPnL = 0 ⇒ -exp(0) = -1."""
    term = ExponentialUtility(gamma=0.5)
    out = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 100.0},
        info={},
    )
    assert out == pytest.approx(-1.0)


def test_positive_pnl_increases_reward_toward_zero():
    """Positive PnL ⇒ reward closer to 0 (less negative)."""
    term = ExponentialUtility(gamma=0.1, pnl_scale=1.0)
    out = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 110.0},
        info={},
    )
    # -exp(-0.1 * 10) = -exp(-1) ≈ -0.3679
    assert out == pytest.approx(-math.exp(-1.0), rel=1e-6)
    assert out > -1.0  # less negative than zero-PnL baseline


def test_negative_pnl_drives_reward_more_negative():
    term = ExponentialUtility(gamma=0.1, pnl_scale=1.0)
    out = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": 90.0},
        info={},
    )
    # -exp(0.1 * 10) = -exp(1) ≈ -2.7183
    assert out == pytest.approx(-math.exp(1.0), rel=1e-6)
    assert out < -1.0


def test_clip_protects_against_overflow():
    term = ExponentialUtility(gamma=0.1, pnl_scale=1.0, clip_pnl=5.0)
    out_huge = term.compute(
        state={"portfolio_value": 100.0},
        action=None,
        next_state={"portfolio_value": -1e9},
        info={},
    )
    # PnL is clipped to -5 (after scale=1), so reward = -exp(0.5) ≈ -1.6487
    assert out_huge == pytest.approx(-math.exp(0.5), rel=1e-6)


def test_invalid_gamma_raises():
    with pytest.raises(ValueError):
        ExponentialUtility(gamma=0.0)
    with pytest.raises(ValueError):
        ExponentialUtility(gamma=-0.1)


def test_higher_gamma_more_risk_averse():
    """Higher γ ⇒ same negative PnL produces a more-negative utility."""
    term_low = ExponentialUtility(gamma=0.1, pnl_scale=1.0, clip_pnl=None)
    term_high = ExponentialUtility(gamma=1.0, pnl_scale=1.0, clip_pnl=None)
    state = {"portfolio_value": 100.0}
    next_state = {"portfolio_value": 95.0}
    out_low = term_low.compute(state=state, action=None, next_state=next_state, info={})
    out_high = term_high.compute(state=state, action=None, next_state=next_state, info={})
    assert out_high < out_low
