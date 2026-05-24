"""Sanity tests for the metaclass-driven RL component registry."""
from __future__ import annotations

import pytest

from aqp.core.registry import build_from_config, list_by_kind
from aqp_rl.core.base import (
    RL_KIND_ACTION,
    RL_KIND_ENV,
    RL_KIND_OBSERVATION,
    RL_KIND_REWARD,
    RL_KIND_TERMINATION,
    RL_KINDS,
    list_rl_components,
)


def test_kinds_have_registered_classes():
    # Importing aqp_rl triggers eager registration via the metaclass.
    import aqp_rl  # noqa: F401

    populated = {k for k in RL_KINDS if list_by_kind(k)}
    # Each canonical kind must have at least one concrete component.
    for required in (
        RL_KIND_ENV,
        RL_KIND_REWARD,
        RL_KIND_OBSERVATION,
        RL_KIND_ACTION,
        RL_KIND_TERMINATION,
    ):
        assert required in populated, f"no components registered for kind {required!r}"


def test_list_rl_components_returns_dict():
    import aqp_rl  # noqa: F401

    everything = list_rl_components()
    assert isinstance(everything, dict)
    assert len(everything) > 0


def test_build_from_config_resolves_continuous_weights_action():
    import aqp_rl  # noqa: F401

    obj = build_from_config(
        {
            "class": "ContinuousWeightsAction",
            "module_path": "aqp_rl.core.action",
            "kwargs": {"n_assets": 3},
        }
    )
    from aqp_rl.core.action import ContinuousWeightsAction

    assert isinstance(obj, ContinuousWeightsAction)
    assert obj.n_assets == 3


def test_termination_predicate_horizon():
    from aqp_rl.terminations.horizon import HorizonTermination

    cond = HorizonTermination()
    assert cond.check(idx=10, horizon=11, env_state={}) is True
    assert cond.check(idx=5, horizon=11, env_state={}) is False


@pytest.mark.parametrize(
    "alias",
    ["StockTradingEnv", "FinRLStockTradingEnv", "FinRLPortfolioCovEnv"],
)
def test_canonical_envs_registered(alias: str):
    import aqp_rl  # noqa: F401

    envs = list_by_kind("rl_env")
    assert alias in envs, f"env {alias!r} should be registered as kind=rl_env"
