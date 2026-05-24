"""Observation-builder shape + composition tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp_rl.core.observation import StackedObservationBuilder
from aqp_rl.observations.lookback import LookbackStackBuilder
from aqp_rl.observations.portfolio_state import PortfolioStateBuilder
from aqp_rl.observations.technical import TechnicalIndicatorBuilder
from aqp_rl.observations.turbulence import TurbulenceBuilder


def test_portfolio_state_builder_shape():
    builder = PortfolioStateBuilder(n_assets=3)
    state = {"weights": [0.4, 0.3, 0.3], "portfolio_value": 100.0}
    obs = builder.build(0, state)
    assert obs.shape == (4,)
    assert builder.output_shape == (4,)
    assert "cash_ratio" in builder.feature_names()


def test_technical_builder_handles_missing_table():
    builder = TechnicalIndicatorBuilder(n_assets=3, indicators=["macd", "rsi_14"])
    obs = builder.build(0, {"feature_tables": {}})
    assert obs.shape == (6,)
    assert all(v == 0 for v in obs)


def test_turbulence_builder_reads_series():
    series = pd.Series([1.0, 2.0, 3.0], index=[0, 1, 2])
    builder = TurbulenceBuilder(scale=1.0)
    out = builder.build(2, {"turbulence": series})
    assert out[0] == pytest.approx(3.0)


def test_lookback_stack_zero_when_missing():
    builder = LookbackStackBuilder(n_assets=2, feature_columns=["macd"], lookback=3)
    out = builder.build(5, {"feature_tables": {}})
    assert out.shape == (2 * 1 * 3,)


def test_stacked_builder_concatenates():
    s1 = PortfolioStateBuilder(n_assets=2)
    s2 = PortfolioStateBuilder(n_assets=2)
    stacked = StackedObservationBuilder(builders=[s1, s2])
    state = {"weights": [0.5, 0.5], "portfolio_value": 100.0}
    out = stacked.build(0, state)
    assert out.shape == (6,)
    assert stacked.output_shape == (6,)


def test_stacked_builder_handles_dict_specs():
    stacked = StackedObservationBuilder(
        builders=[
            {
                "class": "PortfolioStateBuilder",
                "module_path": "aqp_rl.observations.portfolio_state",
                "kwargs": {"n_assets": 2},
            }
        ]
    )
    out = stacked.build(0, {"weights": [0.4, 0.6], "portfolio_value": 100.0})
    assert out.shape == (3,)
