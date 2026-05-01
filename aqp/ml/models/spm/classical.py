"""Classical ML forecasters from SPM (ARIMA, Prophet, GARCH, BayesianRidge).

These don't use the ``TorchForecasterBase``; they implement
:class:`aqp.ml.base.Model` directly to keep dependencies optional.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.ml.base import Model, Reweighter

logger = logging.getLogger(__name__)


def _to_array(dataset: Any) -> tuple[np.ndarray, pd.Index | None]:
    """Coerce dataset to a 1-D numpy array and an optional index."""
    if hasattr(dataset, "to_arrays"):
        _features, labels = dataset.to_arrays()
        return labels.astype(float), getattr(dataset, "index", None)
    if isinstance(dataset, pd.Series):
        return dataset.to_numpy(dtype=float), dataset.index
    if isinstance(dataset, pd.DataFrame):
        col = dataset.iloc[:, -1] if "y" not in dataset.columns else dataset["y"]
        return col.to_numpy(dtype=float), dataset.index
    return np.asarray(dataset, dtype=float), None


@register("ARIMAForecaster", source="stock_prediction_models", category="classical", kind="model")
class ARIMAForecaster(Model):
    """ARIMA(p, d, q) forecaster via statsmodels."""

    def __init__(self, p: int = 1, d: int = 1, q: int = 1, horizon: int = 1) -> None:
        self.p = p
        self.d = d
        self.q = q
        self.horizon = horizon
        self._fit_result = None

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from statsmodels.tsa.arima.model import ARIMA
        except ImportError as exc:  # pragma: no cover
            raise ImportError("statsmodels required for ARIMA") from exc
        y, _ = _to_array(dataset)
        self._fit_result = ARIMA(y, order=(self.p, self.d, self.q)).fit()
        return self

    def predict(self, dataset, segment="test"):
        if self._fit_result is None:
            raise RuntimeError("Call fit() first.")
        y, index = _to_array(dataset)
        forecast = self._fit_result.forecast(steps=max(len(y), self.horizon))[: len(y)]
        return pd.Series(forecast, index=index if index is not None else pd.RangeIndex(len(forecast)))


@register("ProphetForecaster", source="stock_prediction_models", category="classical", kind="model")
class ProphetForecaster(Model):
    """Facebook Prophet forecaster (optional dependency)."""

    def __init__(self, horizon_days: int = 30) -> None:
        self.horizon_days = horizon_days
        self._model = None

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from prophet import Prophet
        except ImportError as exc:  # pragma: no cover
            raise ImportError("prophet required for ProphetForecaster (pip install prophet)") from exc
        y, index = _to_array(dataset)
        df = pd.DataFrame({"ds": pd.to_datetime(index) if index is not None else pd.date_range("2020-01-01", periods=len(y)), "y": y})
        self._model = Prophet()
        self._model.fit(df)
        return self

    def predict(self, dataset, segment="test"):
        if self._model is None:
            raise RuntimeError("Call fit() first.")
        y, index = _to_array(dataset)
        n = len(y)
        future = self._model.make_future_dataframe(periods=n)
        forecast = self._model.predict(future)["yhat"].tail(n)
        idx = pd.to_datetime(index) if index is not None else pd.RangeIndex(n)
        return pd.Series(forecast.values, index=idx)


@register("GARCHForecaster", source="stock_prediction_models", category="classical", kind="model")
class GARCHForecaster(Model):
    """GARCH(p, q) volatility forecaster via the ``arch`` package."""

    def __init__(self, p: int = 1, q: int = 1, mean: str = "Zero") -> None:
        self.p = p
        self.q = q
        self.mean = mean
        self._fit_result = None

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from arch import arch_model
        except ImportError as exc:  # pragma: no cover
            raise ImportError("arch required for GARCHForecaster (pip install arch)") from exc
        y, _ = _to_array(dataset)
        rets = np.diff(np.log(np.maximum(y, 1e-12)))
        self._fit_result = arch_model(rets * 100, mean=self.mean, vol="GARCH", p=self.p, q=self.q).fit(disp="off")
        return self

    def predict(self, dataset, segment="test"):
        if self._fit_result is None:
            raise RuntimeError("Call fit() first.")
        y, index = _to_array(dataset)
        n = len(y)
        forecast = self._fit_result.forecast(horizon=n).variance.values[-1, :n]
        idx = index if index is not None else pd.RangeIndex(n)
        return pd.Series(np.sqrt(forecast) / 100, index=idx, name="volatility")


@register("BayesianRidgeForecaster", source="stock_prediction_models", category="bayesian", kind="model")
class BayesianRidgeForecaster(Model):
    """sklearn ``BayesianRidge`` on lagged features."""

    def __init__(self, n_lags: int = 5) -> None:
        self.n_lags = n_lags
        self._model = None

    def fit(self, dataset, reweighter: Reweighter | None = None):
        try:
            from sklearn.linear_model import BayesianRidge
        except ImportError as exc:  # pragma: no cover
            raise ImportError("scikit-learn required for BayesianRidge") from exc
        y, _ = _to_array(dataset)
        if len(y) <= self.n_lags + 1:
            return self
        X = np.column_stack([y[i : len(y) - self.n_lags + i] for i in range(self.n_lags)])
        target = y[self.n_lags :]
        self._model = BayesianRidge()
        self._model.fit(X, target)
        return self

    def predict(self, dataset, segment="test"):
        if self._model is None:
            raise RuntimeError("Call fit() first.")
        y, index = _to_array(dataset)
        if len(y) <= self.n_lags:
            return pd.Series(dtype=float)
        X = np.column_stack([y[i : len(y) - self.n_lags + i] for i in range(self.n_lags)])
        preds = self._model.predict(X)
        idx = index[self.n_lags :] if index is not None else pd.RangeIndex(len(preds))
        return pd.Series(preds, index=idx)


__all__ = [
    "ARIMAForecaster",
    "BayesianRidgeForecaster",
    "GARCHForecaster",
    "ProphetForecaster",
]
