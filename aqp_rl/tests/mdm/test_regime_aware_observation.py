"""``RegimeAwareObservation`` builder tests."""
from __future__ import annotations

import numpy as np
import pytest

from aqp_rl.core.base import RL_KIND_OBSERVATION, list_rl_components
from aqp_rl.observations.regime import RegimeAwareObservation


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_OBSERVATION)
    assert "regime_aware" in registry
    assert registry["regime_aware"] is RegimeAwareObservation


def test_output_shape_and_feature_names():
    b = RegimeAwareObservation(n_regimes=4)
    assert b.output_shape == (4,)
    assert b.feature_names() == ["regime_0", "regime_1", "regime_2", "regime_3"]


def test_precomputed_labels_index_correctly():
    b = RegimeAwareObservation(n_regimes=3, labels=[0, 1, 2, 0, 2])
    one_hot = b.build(0, {})
    np.testing.assert_array_equal(one_hot, [1, 0, 0])
    one_hot = b.build(2, {})
    np.testing.assert_array_equal(one_hot, [0, 0, 1])
    # Out of range ⇒ zeros.
    one_hot = b.build(99, {})
    np.testing.assert_array_equal(one_hot, [0, 0, 0])


def test_env_state_label_used_when_no_precomputed():
    b = RegimeAwareObservation(n_regimes=3)
    one_hot = b.build(0, {"regime_label": 2})
    np.testing.assert_array_equal(one_hot, [0, 0, 1])
    # Missing key ⇒ zeros.
    one_hot = b.build(0, {})
    np.testing.assert_array_equal(one_hot, [0, 0, 0])


def test_invalid_n_regimes_raises():
    with pytest.raises(ValueError):
        RegimeAwareObservation(n_regimes=0)


def test_custom_label_key():
    b = RegimeAwareObservation(n_regimes=3, label_key="custom_label")
    one_hot = b.build(0, {"custom_label": 1})
    np.testing.assert_array_equal(one_hot, [0, 1, 0])


def test_out_of_range_label_yields_zeros():
    b = RegimeAwareObservation(n_regimes=3)
    one_hot = b.build(0, {"regime_label": 99})
    np.testing.assert_array_equal(one_hot, [0, 0, 0])
    one_hot = b.build(0, {"regime_label": -5})
    np.testing.assert_array_equal(one_hot, [0, 0, 0])
