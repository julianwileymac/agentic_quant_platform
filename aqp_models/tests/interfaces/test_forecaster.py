"""Smoke tests for the Forecaster interface."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp_models.interfaces import Forecaster


class _NativeForecaster:
    def forecast(self, history: pd.DataFrame, *, horizon: int) -> np.ndarray:
        last = float(history.iloc[-1, 0]) if len(history) else 0.0
        return np.full(horizon, last + 1.0)


class _HorizonPredictor:
    def predict(self, history: pd.DataFrame, *, horizon: int) -> np.ndarray:
        last = float(history.iloc[-1, 0]) if len(history) else 0.0
        return np.arange(horizon) + last


class _PointPredictor:
    def predict(self, history: pd.DataFrame) -> float:
        return float(history.iloc[-1, 0])


def test_native_forecast_path() -> None:
    history = pd.DataFrame({"x": np.arange(10.0)})
    wrapper = Forecaster(model=_NativeForecaster())
    out = wrapper.forecast(history, horizon=3)
    np.testing.assert_allclose(out.values, [10.0, 10.0, 10.0])
    assert out.metadata.extras["strategy"] == "native_forecast"
    assert len(out.index) == 3


def test_horizon_kwarg_path() -> None:
    history = pd.DataFrame({"x": np.arange(5.0)})
    out = Forecaster(model=_HorizonPredictor()).forecast(history, horizon=2)
    np.testing.assert_allclose(out.values, [4.0, 5.0])


def test_recursive_rollout_fallback() -> None:
    history = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    out = Forecaster(model=_PointPredictor()).forecast(history, horizon=2)
    assert out.values.shape == (2,)
    assert out.metadata.extras["strategy"] == "recursive_rollout"
