"""Facebook Prophet forecaster adapter."""
from __future__ import annotations

import logging
from typing import Any, Iterable

import numpy as np
import pandas as pd

from aqp.core.registry import forecaster
from aqp.ml.applications.forecaster.base import BaseForecaster

logger = logging.getLogger(__name__)


@forecaster("ProphetForecaster")
class ProphetForecaster(BaseForecaster):
    """Minimal Prophet wrapper that speaks :class:`BaseForecaster`."""

    name = "ProphetForecaster"
    supports_exogenous = True
    supports_quantiles = True

    def __init__(
        self,
        daily_seasonality: bool | str = "auto",
        weekly_seasonality: bool | str = "auto",
        yearly_seasonality: bool | str = "auto",
        seasonality_mode: str = "additive",
        changepoint_prior_scale: float = 0.05,
        holidays: pd.DataFrame | None = None,
        country_holidays: str | None = None,
        regressors: Iterable[str] | None = None,
        interval_width: float = 0.8,
    ) -> None:
        super().__init__()
        self.daily_seasonality = daily_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        self.seasonality_mode = seasonality_mode
        self.changepoint_prior_scale = float(changepoint_prior_scale)
        self.holidays = holidays
        self.country_holidays = country_holidays
        self.regressors = list(regressors or [])
        self.interval_width = float(interval_width)
        self._model: Any = None
        self._name: str | None = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None

    def _build(self) -> Any:
        try:
            from prophet import Prophet
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "prophet is not installed. Install the `ml-forecast` extra."
            ) from exc
        model = Prophet(
            daily_seasonality=self.daily_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            yearly_seasonality=self.yearly_seasonality,
            seasonality_mode=self.seasonality_mode,
            changepoint_prior_scale=self.changepoint_prior_scale,
            holidays=self.holidays,
            interval_width=self.interval_width,
        )
        if self.country_holidays:
            model.add_country_holidays(country_name=self.country_holidays)
        for r in self.regressors:
            model.add_regressor(r)
        return model

    def _prophet_df(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None) -> pd.DataFrame:
        if isinstance(y, pd.DataFrame):
            y = y.squeeze()
        frame = pd.DataFrame({"ds": y.index, "y": y.values})
        if X is not None:
            for col in self.regressors:
                if col in X.columns:
                    frame[col] = X[col].values
        return frame

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> ProphetForecaster:
        self._model = self._build()
        df = self._prophet_df(y, X)
        self._model.fit(df)
        self._name = getattr(y, "name", "y") if isinstance(y, pd.Series) else "y"
        if isinstance(y.index, pd.DatetimeIndex):
            self._last_index = y.index[-1]
            self._freq = y.index.inferred_freq
        self._fitted = True
        return self

    def _future_df(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None) -> pd.DataFrame:
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)
        if isinstance(idx, pd.DatetimeIndex):
            future = pd.DataFrame({"ds": idx})
        else:
            step = pd.tseries.frequencies.to_offset(self._freq or "D")
            future = pd.DataFrame(
                {"ds": [self._last_index + step * int(o) for o in idx.values]}
            )
        if X is not None:
            for col in self.regressors:
                if col in X.columns:
                    future[col] = X[col].values[: len(future)]
        return future

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        future = self._future_df(fh, X)
        fc = self._model.predict(future)
        return pd.Series(fc["yhat"].values, index=pd.DatetimeIndex(fc["ds"].values), name=self._name or "yhat")

    def predict_quantiles(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        alpha: list[float] | None = None,
        X: pd.DataFrame | None = None,
    ) -> dict[float, pd.DataFrame]:
        self._ensure_fitted()
        future = self._future_df(fh, X)
        fc = self._model.predict(future)
        out: dict[float, pd.DataFrame] = {}
        for a in (alpha or [self.interval_width]):
            out[a] = pd.DataFrame(
                {"low": fc["yhat_lower"].values, "high": fc["yhat_upper"].values},
                index=pd.DatetimeIndex(fc["ds"].values),
            )
        return out


__all__ = ["ProphetForecaster"]
