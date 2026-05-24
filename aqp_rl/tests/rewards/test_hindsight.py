"""Hindsight reward (DeepScalper pattern) — unit tests."""
from __future__ import annotations

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.hindsight import HindsightReward


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "hindsight" in registry
    assert registry["hindsight"] is HindsightReward


def test_zero_position_yields_zero():
    term = HindsightReward()
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "position": 0,
            "current_price": 100.0,
            "next_price": 110.0,
            "future_price": 120.0,
        },
    )
    assert out == 0.0


def test_long_position_and_rising_price_positive_reward():
    term = HindsightReward(future_weight=0.5)
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "position": 10,
            "current_price": 100.0,
            "next_price": 105.0,
            "future_price": 120.0,
        },
    )
    # 10 * ((105 - 100) + 0.5 * (120 - 100)) = 10 * (5 + 10) = 150
    assert out == pytest.approx(150.0)


def test_short_position_and_falling_price_positive_reward():
    term = HindsightReward(future_weight=0.5)
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "position": -10,
            "current_price": 100.0,
            "next_price": 95.0,
            "future_price": 80.0,
        },
    )
    # -10 * ((95 - 100) + 0.5 * (80 - 100)) = -10 * (-5 - 10) = 150
    assert out == pytest.approx(150.0)


def test_missing_future_price_falls_back_to_immediate():
    """Without ``future_price`` only the immediate PnL term contributes."""
    term = HindsightReward(future_weight=0.5)
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "position": 10,
            "current_price": 100.0,
            "next_price": 105.0,
        },
    )
    # 10 * (105 - 100) = 50
    assert out == pytest.approx(50.0)


def test_future_weight_zero_ignores_hindsight():
    term = HindsightReward(future_weight=0.0)
    out = term.compute(
        state={},
        action=None,
        next_state={},
        info={
            "position": 10,
            "current_price": 100.0,
            "next_price": 105.0,
            "future_price": 1000.0,
        },
    )
    assert out == pytest.approx(50.0)


def test_negative_future_weight_raises():
    with pytest.raises(ValueError):
        HindsightReward(future_weight=-0.1)


def test_missing_position_or_prices_yields_zero():
    term = HindsightReward()
    assert term.compute(state={}, action=None, next_state={}, info={}) == 0.0
    assert (
        term.compute(state={}, action=None, next_state={}, info={"position": 1}) == 0.0
    )
    assert (
        term.compute(
            state={},
            action=None,
            next_state={},
            info={"position": 1, "current_price": 100.0},
        )
        == 0.0
    )
