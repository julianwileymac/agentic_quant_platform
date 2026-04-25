"""Auto-ARIMA selector via ``pmdarima``."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.core.registry import forecaster
from aqp.ml.applications.forecaster.base import BaseForecaster

logger = logging.getLogger(__name__)


@forecaster("AutoARIMAForecaster")
class AutoARIMAForecaster(BaseForecaster):
    """Auto-searched ARIMA / SARIMAX — thin wrapper around ``pmdarima.auto_arima``."""

    name = "AutoARIMAForecaster"
    supports_exogenous = True
    supports_quantiles = True

    def __init__(
        self,
        seasonal: bool = False,
        m: int = 1,
        max_p: int = 5,
        max_q: int = 5,
        max_d: int = 2,
        information_criterion: str = "aic",
    ) -> None:
        super().__init__()
        self.seasonal = bool(seasonal)
        self.m = int(m)
        self.max_p = int(max_p)
        self.max_q = int(max_q)
        self.max_d = int(max_d)
        self.information_criterion = information_criterion
        self._model: Any = None
        self._last_index: pd.Timestamp | None = None
        self._freq: str | None = None
        self._name: str | None = None

    def fit(self, y: pd.Series | pd.DataFrame, X: pd.DataFrame | None = None) -> AutoARIMAForecaster:
        try:
            import pmdarima as pm
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "pmdarima is not installed. Install the `ml-forecast` extra."
            ) from exc
        y_s = y.squeeze() if isinstance(y, pd.DataFrame) else y
        self._model = pm.auto_arima(
            y_s,
            X=X,
            seasonal=self.seasonal,
            m=self.m,
            max_p=self.max_p,
            max_q=self.max_q,
            max_d=self.max_d,
            information_criterion=self.information_criterion,
            error_action="ignore",
            suppress_warnings=True,
        )
        self._name = getattr(y_s, "name", "y")
        if isinstance(y_s.index, pd.DatetimeIndex):
            self._last_index = y_s.index[-1]
            self._freq = y_s.index.inferred_freq
        self._fitted = True
        return self

    def predict(self, fh: int | list[int] | pd.DatetimeIndex, X: pd.DataFrame | None = None) -> pd.Series:
        self._ensure_fitted()
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        fc = self._model.predict(n_periods=steps, X=X)
        idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)[: len(fc)]
        return pd.Series(fc, index=idx, name=self._name or "yhat")

    def predict_quantiles(
        self,
        fh: int | list[int] | pd.DatetimeIndex,
        alpha: list[float] | None = None,
        X: pd.DataFrame | None = None,
    ) -> dict[float, pd.DataFrame]:
        self._ensure_fitted()
        alpha = alpha or [0.9]
        steps = fh if isinstance(fh, int) else (len(fh) if hasattr(fh, "__len__") else int(fh))
        out: dict[float, pd.DataFrame] = {}
        for a in alpha:
            point, ci = self._model.predict(
                n_periods=steps, X=X, return_conf_int=True, alpha=1 - a
            )
            idx = self._coerce_fh(fh, last_index=self._last_index, freq=self._freq)[: len(point)]
            out[a] = pd.DataFrame(
                {"low": ci[:, 0], "high": ci[:, 1]},
                index=idx,
            )
        return out


__all__ = ["AutoARIMAForecaster"]
