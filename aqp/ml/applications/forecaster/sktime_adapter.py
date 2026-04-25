"""sktime bridge — wrap any sktime ``BaseForecaster`` subclass in AQP's
:class:`BaseForecaster` protocol so platform-side pipelines don't need to
know about sktime's ``ForecastingHorizon`` object.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.core.registry import forecaster
from aqp.ml.applications.forecaster.base import BaseForecaster

logger = logging.getLogger(__name__)


@forecaster("SktimeForecaster")
class SktimeForecaster(BaseForecaster):
    """Adapter: ``SktimeForecaster(estimator=<any sktime.forecasting.*>)``."""

    name = "SktimeForecaster"
    supports_quantiles = True

    def __init__(self, estimator: Any) -> None:
        super().__init__()
        self.estimator = estimator
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None
        self._name: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> SktimeForecaster:
        self.estimator.fit(y, X=X)
        y_s = y.squeeze() if isinstance(y, pd.DataFrame) else y
        self._name = getattr(y_s, "name", "y")
        if isinstance(y_s.index, pd.DatetimeIndex):
            self._last_index = y_s.index[-1]
            self._freq = y_s.index.inferred_freq
        self._fitted = True
        return self

    def _fh(self, fh: int | list[int] | pd.DatetimeIndex) -> Any:
        from sktime.forecasting.base import ForecastingHorizon

        if isinstance(fh, pd.DatetimeIndex):
            return ForecastingHorizon(fh, is_relative=False)
        if isinstance(fh, int):
            return ForecastingHorizon(list(range(1, fh + 1)), is_relative=True)
        return ForecastingHorizon(list(fh), is_relative=True)

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        yhat = self.estimator.predict(self._fh(fh), X=X)
        if isinstance(yhat, pd.DataFrame):
            yhat = yhat.squeeze()
        if self._name:
            yhat.name = self._name
        return yhat

    def predict_quantiles(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        alpha: list[float] | None = None,
        X: pd.DataFrame | None = None,
    ) -> dict[float, pd.DataFrame]:
        self._ensure_fitted()
        alpha = alpha or [0.9]
        out: dict[float, pd.DataFrame] = {}
        try:
            for a in alpha:
                intervals = self.estimator.predict_interval(
                    fh=self._fh(fh), X=X, coverage=a
                )
                low = intervals.xs("lower", axis=1, level=-1).squeeze()
                high = intervals.xs("upper", axis=1, level=-1).squeeze()
                out[a] = pd.DataFrame({"low": low.values, "high": high.values}, index=low.index)
        except Exception:
            logger.debug("predict_interval not supported by estimator", exc_info=True)
        return out


__all__ = ["SktimeForecaster"]
