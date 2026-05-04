"""Quick time-series helpers for notebooks (ARIMA / ETS / Prophet / decompose)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class QuickForecastResult:
    backend: str
    horizon: int
    forecast: pd.Series
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "horizon": self.horizon,
            "forecast": [
                {"timestamp": str(idx), "value": float(val)}
                for idx, val in self.forecast.items()
            ],
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


@dataclass
class QuickDecomposeResult:
    period: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"period": self.period, "rows": self.rows, "metrics": self.metrics}


def _coerce_series(series: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        if series.shape[1] == 0:
            raise ValueError("DataFrame is empty")
        series = series.iloc[:, 0]
    series = pd.Series(series).dropna().astype(float)
    if series.empty:
        raise ValueError("Series has no usable values")
    if not isinstance(series.index, pd.DatetimeIndex):
        try:
            series.index = pd.to_datetime(series.index)
        except Exception as exc:
            raise ValueError("Series index must be coercible to DatetimeIndex") from exc
    return series.sort_index()


def quick_arima(
    series: pd.Series,
    *,
    horizon: int = 20,
    order: tuple[int, int, int] = (1, 1, 1),
    seasonal_order: tuple[int, int, int, int] | None = None,
) -> QuickForecastResult:
    """Fit a (S)ARIMA model and return ``horizon`` future steps."""
    y = _coerce_series(series)
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install the `ml` extra."
        ) from exc
    fit = SARIMAX(
        y,
        order=tuple(order),
        seasonal_order=tuple(seasonal_order) if seasonal_order else (0, 0, 0, 0),
        enforce_stationarity=False,
        enforce_invertibility=False,
    ).fit(disp=False)
    pred = fit.get_forecast(steps=int(horizon)).predicted_mean
    if not isinstance(pred, pd.Series):
        pred = pd.Series(pred)
    return QuickForecastResult(
        backend="arima",
        horizon=int(horizon),
        forecast=pred,
        metrics={"aic": float(fit.aic), "bic": float(fit.bic)},
        metadata={"order": list(order), "seasonal_order": list(seasonal_order or (0, 0, 0, 0))},
    )


def quick_ets(
    series: pd.Series,
    *,
    horizon: int = 20,
    trend: str | None = "add",
    seasonal: str | None = None,
    seasonal_periods: int | None = None,
) -> QuickForecastResult:
    """Fit an exponential-smoothing model (Holt-Winters)."""
    y = _coerce_series(series)
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install the `ml` extra."
        ) from exc
    model = ExponentialSmoothing(
        y,
        trend=trend,
        seasonal=seasonal,
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    ).fit()
    pred = model.forecast(int(horizon))
    return QuickForecastResult(
        backend="ets",
        horizon=int(horizon),
        forecast=pred,
        metrics={"aic": float(model.aic), "bic": float(model.bic)},
        metadata={
            "trend": trend,
            "seasonal": seasonal,
            "seasonal_periods": seasonal_periods,
        },
    )


def quick_prophet(
    series: pd.Series,
    *,
    horizon: int = 20,
    forecaster_kwargs: dict[str, Any] | None = None,
) -> QuickForecastResult:
    """Fit a Prophet model via the AQP adapter."""
    y = _coerce_series(series)
    try:
        from aqp.ml.applications.forecaster.prophet_adapter import ProphetForecaster
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Prophet adapter unavailable. Install the `ml-forecast` extra."
        ) from exc
    forecaster = ProphetForecaster(**(forecaster_kwargs or {}))
    forecaster.fit(y)
    pred = forecaster.predict(int(horizon))
    return QuickForecastResult(
        backend="prophet",
        horizon=int(horizon),
        forecast=pred,
        metadata={"n_train": int(len(y))},
    )


def quick_decompose(
    series: pd.Series,
    *,
    period: int = 20,
    robust: bool = True,
    max_rows: int = 1000,
) -> QuickDecomposeResult:
    """STL-decompose a series into trend / seasonal / residual."""
    y = _coerce_series(series)
    try:
        from statsmodels.tsa.seasonal import STL
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install the `ml` extra."
        ) from exc
    if len(y) < max(3, period * 2):
        rows = [
            {"timestamp": str(ts), "observed": float(val)}
            for ts, val in y.items()
        ]
        return QuickDecomposeResult(period=int(period), rows=rows[:max_rows])
    fit = STL(y, period=int(period), robust=bool(robust)).fit()
    rows = [
        {
            "timestamp": str(ts),
            "observed": float(y.iloc[i]),
            "trend": float(fit.trend.iloc[i]),
            "seasonal": float(fit.seasonal.iloc[i]),
            "resid": float(fit.resid.iloc[i]),
        }
        for i, ts in enumerate(y.index[:max_rows])
    ]
    return QuickDecomposeResult(
        period=int(period),
        rows=rows,
        metrics={
            "n": int(len(y)),
            "trend_std": float(np.nanstd(fit.trend)),
            "seasonal_std": float(np.nanstd(fit.seasonal)),
            "resid_std": float(np.nanstd(fit.resid)),
        },
    )


__all__ = [
    "QuickDecomposeResult",
    "QuickForecastResult",
    "quick_arima",
    "quick_decompose",
    "quick_ets",
    "quick_prophet",
]
