"""Action-space transform tests."""
from __future__ import annotations

import numpy as np
from gymnasium import spaces

from aqp.rl.core.action import (
    ContinuousWeightsAction,
    DiscreteBuySellHoldAction,
    IntegerSharesAction,
    SoftmaxWeightsAction,
)


def test_continuous_weights_renormalises_when_sum_exceeds_one():
    space = ContinuousWeightsAction(n_assets=3, max_weight=1.0)
    out = space.transform([0.6, 0.7, 0.8])
    assert isinstance(out, np.ndarray)
    assert abs(np.sum(np.abs(out))) <= 1.0 + 1e-6


def test_softmax_action_normalises_to_simplex():
    space = SoftmaxWeightsAction(n_assets=4)
    out = space.transform([0.2, 0.3, 0.4, 0.1])
    assert np.isclose(np.sum(out), 1.0)


def test_integer_shares_action_returns_int_dtype():
    space = IntegerSharesAction(n_assets=3, hmax=10)
    out = space.transform([0.5, -0.2, 0.0])
    assert out.dtype == np.int64
    assert out.tolist() == [5, -2, 0]


def test_discrete_buy_sell_hold_gym_space():
    space = DiscreteBuySellHoldAction()
    assert isinstance(space.gym_space(), spaces.Discrete)
    assert space.transform([1]) == 1
    assert space.transform([2]) == 2
