"""Statsmodels-backed forecasters.

Covers the four workhorses every quant research notebook eventually
needs:

* :class:`ARIMAForecaster` — ``(p, d, q)`` ARIMA.
* :class:`SARIMAXForecaster` — seasonal + exogenous.
* :class:`VARForecaster` — vector autoregression for multivariate series.
* :class:`VECMForecaster` — vector error correction (cointegrated).

All implement :class:`aqp.ml.applications.forecaster.base.BaseForecaster`.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import forecaster
from aqp.ml.applications.forecaster.base import BaseForecaster

logger = logging.getLogger(__name__)


@forecaster("ARIMAForecaster")
class ARIMAForecaster(BaseForecaster):
    """Classical ``ARIMA(p, d, q)`` forecaster."""

    name = "ARIMAForecaster"
    supports_quantiles = True

    def __init__(self, order: tuple[int, int, int] = (1, 0, 0), trend: str | None = "c") -> None:
        super().__init__()
        self.order = tuple(order)
        self.trend = trend
        self._result: Any = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None
        self._name: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> ARIMAForecaster:
        from statsmodels.tsa.arima.model import ARIMA

        y_s = y.squeeze() if isinstance(y, pd.DataFrame) else y
        model = ARIMA(y_s, order=self.order, trend=self.trend, exog=X)
        self._result = model.fit()
        if isinstance(y_s.index, pd.DatetimeIndex):
            self._last_index = y_s.index[-1]
            self._freq = y_s.index.inferred_freq
        self._name = getattr(y_s, "name", "y")
        self._fitted = True
        return self

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        forecast = self._result.forecast(steps=steps, exog=X)
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)
        return pd.Series(np.asarray(forecast), index=idx[: len(forecast)], name=self._name or "yhat")

    def predict_quantiles(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        alpha: list[float] | None = None,
        X: pd.DataFrame | None = None,
    ) -> dict[float, pd.DataFrame]:
        self._ensure_fitted()
        alpha = alpha or [0.9]
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        forecast_res = self._result.get_forecast(steps=steps, exog=X)
        mean = forecast_res.predicted_mean
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)[: len(mean)]
        out: dict[float, pd.DataFrame] = {}
        for a in alpha:
            ci = forecast_res.conf_int(alpha=1 - a)
            out[a] = pd.DataFrame(
                {"low": ci.iloc[:, 0].values, "high": ci.iloc[:, 1].values},
                index=idx,
            )
        return out


@forecaster("SARIMAXForecaster")
class SARIMAXForecaster(BaseForecaster):
    name = "SARIMAXForecaster"
    supports_exogenous = True
    supports_quantiles = True

    def __init__(
        self,
        order: tuple[int, int, int] = (1, 0, 0),
        seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0),
        trend: str | None = "c",
    ) -> None:
        super().__init__()
        self.order = tuple(order)
        self.seasonal_order = tuple(seasonal_order)
        self.trend = trend
        self._result: Any = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None
        self._name: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> SARIMAXForecaster:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        y_s = y.squeeze() if isinstance(y, pd.DataFrame) else y
        model = SARIMAX(
            y_s,
            exog=X,
            order=self.order,
            seasonal_order=self.seasonal_order,
            trend=self.trend,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        self._result = model.fit(disp=False)
        if isinstance(y_s.index, pd.DatetimeIndex):
            self._last_index = y_s.index[-1]
            self._freq = y_s.index.inferred_freq
        self._name = getattr(y_s, "name", "y")
        self._fitted = True
        return self

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        forecast = self._result.forecast(steps=steps, exog=X)
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)
        return pd.Series(np.asarray(forecast), index=idx[: len(forecast)], name=self._name or "yhat")


@forecaster("VARForecaster")
class VARForecaster(BaseForecaster):
    name = "VARForecaster"
    supports_quantiles = False

    def __init__(self, lags: int = 1) -> None:
        super().__init__()
        self.lags = int(lags)
        self._result: Any = None
        self._names: list[str] | None = None
        self._last_rows: np.ndarray | None = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> VARForecaster:
        from statsmodels.tsa.api import VAR

        if not isinstance(y, pd.DataFrame):
            raise ValueError("VAR requires a multivariate DataFrame y.")
        model = VAR(y)
        self._result = model.fit(self.lags)
        self._names = list(y.columns)
        self._last_rows = y.iloc[-self.lags :].values
        if isinstance(y.index, pd.DatetimeIndex):
            self._last_index = y.index[-1]
            self._freq = y.index.inferred_freq
        self._fitted = True
        return self

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        fc = self._result.forecast(self._last_rows, steps=steps)
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)[: fc.shape[0]]
        cols = self._names or [f"y{i}" for i in range(fc.shape[1])]
        return pd.DataFrame(fc, columns=cols, index=idx).stack().rename("yhat")


@forecaster("VECMForecaster")
class VECMForecaster(BaseForecaster):
    name = "VECMForecaster"
    supports_quantiles = False

    def __init__(self, k_ar_diff: int = 1, coint_rank: int = 1) -> None:
        super().__init__()
        self.k_ar_diff = int(k_ar_diff)
        self.coint_rank = int(coint_rank)
        self._result: Any = None
        self._names: list[str] | None = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> VECMForecaster:
        from statsmodels.tsa.vector_ar.vecm import VECM

        if not isinstance(y, pd.DataFrame):
            raise ValueError("VECM requires a multivariate DataFrame y.")
        model = VECM(y, k_ar_diff=self.k_ar_diff, coint_rank=self.coint_rank)
        self._result = model.fit()
        self._names = list(y.columns)
        if isinstance(y.index, pd.DatetimeIndex):
            self._last_index = y.index[-1]
            self._freq = y.index.inferred_freq
        self._fitted = True
        return self

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        fc = self._result.predict(steps=steps)
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)[: fc.shape[0]]
        cols = self._names or [f"y{i}" for i in range(fc.shape[1])]
        return pd.DataFrame(fc, columns=cols, index=idx).stack().rename("yhat")


__all__ = [
    "ARIMAForecaster",
    "SARIMAXForecaster",
    "VARForecaster",
    "VECMForecaster",
]
