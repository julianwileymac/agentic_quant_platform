"""Unified forecaster facade.

A single contract so call-sites can plug in:

* classical statistical forecasters (ARIMA / SARIMAX / VAR / VECM via
  :mod:`statsmodels`),
* Prophet,
* any :mod:`sktime` ``BaseForecaster`` subclass,
* the LLM-backed :class:`~aqp.ml.applications.forecaster.forecaster.FinGPTForecaster`,

...without caring which backend is underneath.

The surface mirrors the sktime ``BaseForecaster`` protocol (``fit`` /
``predict`` / ``predict_quantiles``) so existing sktime pipelines compose
naturally. Concrete adapters live alongside this module:

* ``statsmodels_adapter.py``
* ``prophet_adapter.py``
* ``sktime_adapter.py``
* ``auto_arima.py``
* ``fingpt_forecaster.py`` (existing — wraps the LLM forecaster as a BaseForecaster)

Classes registered with :func:`aqp.core.registry.forecaster` are browsable
via :func:`aqp.core.registry.list_by_kind('forecaster')`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.base import Serializable

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Structured forecast output common to every backend.

    ``point`` is the point forecast indexed by the forecast horizon. When
    the backend supports quantiles, ``quantiles`` maps ``alpha`` → DataFrame
    with ``low`` / ``high`` columns for each horizon step.
    """

    point: pd.Series
    quantiles: dict[float, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_frame(self) -> pd.DataFrame:
        frame = self.point.rename("yhat").to_frame()
        for alpha, q in self.quantiles.items():
            frame[f"q{int(alpha * 100):02d}_low"] = q["low"]
            frame[f"q{int(alpha * 100):02d}_high"] = q["high"]
        return frame


class BaseForecaster(Serializable, ABC):
    """Backend-agnostic forecaster contract.

    Subclasses typically hold a single underlying estimator (statsmodels
    result, Prophet model, sktime forecaster, LLM client, ...) and delegate
    to it in :meth:`fit` / :meth:`predict`. A minimal ``Naive`` forecaster
    is provided below so pipelines that reference a forecaster config can
    fall back to it when the heavier dependencies are unavailable.
    """

    # Informational — surfaced in UI catalog. Set by subclasses.
    name: str = "BaseForecaster"
    supports_exogenous: bool = False
    supports_quantiles: bool = False

    def __init__(self) -> None:
        self._fitted: bool = False

    # ---- lifecycle -----------------------------------------------------

    @abstractmethod
    def fit(
        self,
        y: pd.Series | pd.DataFrame,
        X: pd.DataFrame | None = None,
    ) -> BaseForecaster:
        """Fit the forecaster. Returns ``self`` for chaining."""

    @abstractmethod
    def predict(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        X: pd.DataFrame | None = None,
    ) -> pd.Series:
        """Return the point forecast for the requested horizon."""

    # Optional — default raises so callers can detect unsupported backends.
    def predict_quantiles(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        alpha: list[float] | None = None,
        X: pd.DataFrame | None = None,
    ) -> dict[float, pd.DataFrame]:
        raise NotImplementedError(
            f"{type(self).__name__} does not support predict_quantiles"
        )

    def forecast(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        X: pd.DataFrame | None = None,
        alpha: list[float] | None = None,
    ) -> ForecastResult:
        """Convenience wrapper returning a :class:`ForecastResult`."""
        point = self.predict(fh, X=X)
        quantiles: dict[float, pd.DataFrame] = {}
        if alpha and self.supports_quantiles:
            try:
                quantiles = self.predict_quantiles(fh, alpha=alpha, X=X)
            except NotImplementedError:
                quantiles = {}
        return ForecastResult(
            point=point,
            quantiles=quantiles,
            metadata={"name": self.name, "supports_exogenous": self.supports_exogenous},
        )

    # ---- helpers -------------------------------------------------------

    def _ensure_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError(f"{type(self).__name__} must be fit before predict()")

    @staticmethod
    def _coerce_fh(
        fh: int | list[int] | pd.DatetimeIndex,
        *,
        last_index: pd.Timestamp | None = None,
        freq: str | None = None,
    ) -> pd.Index:
        """Normalise a forecast horizon spec into a pandas index.

        - ``int N`` → next ``N`` integer steps (``[1..N]``).
        - ``list[int]`` → integer offsets (``[1, 5, 10]`` = h=1, h=5, h=10).
        - ``DatetimeIndex`` → used as-is.
        """
        if isinstance(fh, pd.DatetimeIndex):
            return fh
        if isinstance(fh, int):
            offsets = list(range(1, fh + 1))
        else:
            offsets = list(fh)
        if last_index is not None and freq is not None:
            try:
                step = pd.tseries.frequencies.to_offset(freq)
                return pd.DatetimeIndex([last_index + step * int(o) for o in offsets])
            except Exception:
                pass
        return pd.Index(offsets, name="h")


# ---------------------------------------------------------------------------
# NaiveForecaster — zero-dependency fallback used in tests and when extras
# (prophet / statsmodels / sktime) are unavailable.
# ---------------------------------------------------------------------------


class NaiveForecaster(BaseForecaster):
    """Minimal forecaster that projects the last observed value forward.

    Supports three strategies:

    * ``last`` — repeat the last value (random-walk assumption).
    * ``mean`` — repeat the training mean.
    * ``drift`` — linear drift using first+last training values.

    Registered so pipelines referencing ``NaiveForecaster`` always resolve
    even when optional deps are missing.
    """

    name = "NaiveForecaster"

    def __init__(self, strategy: str = "last") -> None:
        super().__init__()
        if strategy not in {"last", "mean", "drift"}:
            raise ValueError(f"Unsupported strategy {strategy!r}")
        self.strategy = strategy
        self._last_value: float | None = None
        self._mean_value: float | None = None
        self._first_value: float | None = None
        self._n_train: int = 0
        self._y_name: str | None = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None

    def fit(
        self,
        y: pd.Series | pd.DataFrame,
        X: pd.DataFrame | None = None,
    ) -> NaiveForecaster:
        series = y.squeeze() if isinstance(y, pd.DataFrame) else y
        if series.empty:
            raise ValueError("NaiveForecaster: empty y.")
        self._first_value = float(series.iloc[0])
        self._last_value = float(series.iloc[-1])
        self._mean_value = float(series.mean())
        self._n_train = int(len(series))
        self._y_name = series.name if isinstance(series, pd.Series) else "y"
        if isinstance(series.index, pd.DatetimeIndex):
            self._last_index = series.index[-1]
            self._freq = series.index.inferred_freq
        self._fitted = True
        return self

    def predict(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        X: pd.DataFrame | None = None,
    ) -> pd.Series:
        self._ensure_fitted()
        index = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)
        n = len(index)
        if self.strategy == "last":
            values = np.full(n, float(self._last_value or 0.0))
        elif self.strategy == "mean":
            values = np.full(n, float(self._mean_value or 0.0))
        else:  # drift
            n_train = max(self._n_train - 1, 1)
            slope = ((self._last_value or 0.0) - (self._first_value or 0.0)) / n_train
            offsets = np.arange(1, n + 1) if not isinstance(index, pd.DatetimeIndex) else np.arange(1, n + 1)
            values = np.asarray(self._last_value or 0.0) + slope * offsets
        return pd.Series(values, index=index, name=self._y_name or "yhat")


__all__ = [
    "BaseForecaster",
    "ForecastResult",
    "NaiveForecaster",
]
