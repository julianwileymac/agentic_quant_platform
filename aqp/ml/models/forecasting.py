"""Forecasting adapters that expose Prophet/sktime through ``aqp.ml.Model``."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import build_from_config, register
from aqp.ml.base import Model, Reweighter
from aqp.ml.models._utils import prepare_panel, split_xy


def _label_series(panel: pd.DataFrame) -> pd.Series:
    _, y, _ = split_xy(panel)
    idx = panel.index if isinstance(panel.index, pd.MultiIndex) else pd.RangeIndex(len(panel))
    return pd.Series(np.asarray(y, dtype=float), index=idx, name="label")


def _fit_series_by_symbol(panel: pd.DataFrame) -> dict[str, pd.Series]:
    y = _label_series(panel)
    if isinstance(y.index, pd.MultiIndex):
        names = list(y.index.names)
        sym_level = names.index("vt_symbol") if "vt_symbol" in names else 1
        ts_level = names.index("datetime") if "datetime" in names else 0
        out: dict[str, pd.Series] = {}
        for vt_symbol, sub in y.groupby(level=sym_level):
            sub = sub.droplevel(sym_level)
            if isinstance(sub.index, pd.MultiIndex):
                sub.index = sub.index.get_level_values(ts_level)
            sub.index = pd.to_datetime(sub.index)
            out[str(vt_symbol)] = sub.sort_index().dropna()
        return out
    idx = pd.to_datetime(y.index, errors="coerce")
    return {"__single__": pd.Series(y.values, index=idx, name="label").dropna()}


def _segment_index_by_symbol(panel: pd.DataFrame) -> dict[str, pd.Index]:
    if isinstance(panel.index, pd.MultiIndex):
        names = list(panel.index.names)
        sym_level = names.index("vt_symbol") if "vt_symbol" in names else 1
        return {
            str(vt_symbol): sub.index
            for vt_symbol, sub in panel.groupby(level=sym_level, sort=False)
        }
    return {"__single__": panel.index}


class _ForecasterModel(Model):
    def __init__(self, horizon: int | None = None) -> None:
        self.horizon = int(horizon) if horizon else None
        self.forecasters_: dict[str, Any] = {}

    def _build_forecaster(self) -> Any:
        raise NotImplementedError

    def fit(self, dataset: Any, reweighter: Reweighter | None = None) -> _ForecasterModel:
        del reweighter
        series_by_symbol = _fit_series_by_symbol(prepare_panel(dataset, "train"))
        self.forecasters_.clear()
        for vt_symbol, y in series_by_symbol.items():
            if len(y) < 2:
                continue
            forecaster = self._build_forecaster()
            forecaster.fit(y)
            self.forecasters_[vt_symbol] = forecaster
        return self

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        if not self.forecasters_:
            raise RuntimeError(f"{type(self).__name__}.predict called before fit().")
        seg = segment if isinstance(segment, str) else "test"
        panel = prepare_panel(dataset, seg)
        segment_index = _segment_index_by_symbol(panel)
        parts: list[pd.Series] = []
        for vt_symbol, idx in segment_index.items():
            forecaster = self.forecasters_.get(vt_symbol) or next(iter(self.forecasters_.values()))
            n = self.horizon or len(idx)
            try:
                yhat = forecaster.predict(n)
            except TypeError:
                yhat = forecaster.predict(fh=n)
            values = np.asarray(yhat, dtype=float).reshape(-1)
            if len(values) < len(idx):
                values = np.pad(values, (0, len(idx) - len(values)), mode="edge")
            parts.append(pd.Series(values[: len(idx)], index=idx, name="score"))
        if not parts:
            return pd.Series(dtype=float, name="score")
        return pd.concat(parts).sort_index()


@register("ProphetForecastModel")
class ProphetForecastModel(_ForecasterModel):
    """DatasetH-compatible wrapper around the existing Prophet forecaster."""

    def __init__(self, horizon: int | None = None, forecaster_kwargs: dict[str, Any] | None = None) -> None:
        super().__init__(horizon=horizon)
        self.forecaster_kwargs = dict(forecaster_kwargs or {})

    def _build_forecaster(self) -> Any:
        from aqp.ml.applications.forecaster.prophet_adapter import ProphetForecaster

        return ProphetForecaster(**self.forecaster_kwargs)


@register("SktimeForecastModel")
class SktimeForecastModel(_ForecasterModel):
    """DatasetH-compatible wrapper around an sktime forecaster."""

    def __init__(
        self,
        estimator_cfg: dict[str, Any] | None = None,
        horizon: int | None = None,
    ) -> None:
        super().__init__(horizon=horizon)
        self.estimator_cfg = deepcopy(estimator_cfg or {})

    def _build_forecaster(self) -> Any:
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        if self.estimator_cfg:
            estimator = build_from_config(self.estimator_cfg)
        else:
            try:
                from sktime.forecasting.naive import NaiveForecaster
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError("sktime is not installed. Install the `ml-forecast` extra.") from exc
            estimator = NaiveForecaster(strategy="last")
        return SktimeForecaster(estimator=estimator)


@register("SktimeReductionForecastModel")
class SktimeReductionForecastModel(SktimeForecastModel):
    """sktime reduction forecaster backed by a sklearn regressor."""

    def __init__(
        self,
        regressor_cfg: dict[str, Any] | None = None,
        window_length: int = 20,
        strategy: str = "recursive",
        horizon: int | None = None,
    ) -> None:
        super().__init__(estimator_cfg=None, horizon=horizon)
        self.regressor_cfg = deepcopy(regressor_cfg or {})
        self.window_length = int(window_length)
        self.strategy = str(strategy)

    def _build_forecaster(self) -> Any:
        try:
            from sklearn.linear_model import Ridge
            from sktime.forecasting.compose import make_reduction
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("sktime and scikit-learn are required. Install `ml-forecast,ml`.") from exc
        estimator = build_from_config(self.regressor_cfg) if self.regressor_cfg else Ridge()
        reduced = make_reduction(
            estimator,
            window_length=self.window_length,
            strategy=self.strategy,
        )
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        return SktimeForecaster(estimator=reduced)


@register("AutoETSForecastModel", kind="model")
class AutoETSForecastModel(_ForecasterModel):
    """sktime AutoETS — automatic exponential smoothing model selection."""

    def __init__(
        self,
        horizon: int | None = None,
        seasonal_periods: int | None = None,
        information_criterion: str = "aic",
        sp: int | None = None,
    ) -> None:
        super().__init__(horizon=horizon)
        self.seasonal_periods = seasonal_periods
        self.information_criterion = str(information_criterion)
        self.sp = sp

    def _build_forecaster(self) -> Any:
        try:
            from sktime.forecasting.ets import AutoETS
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "sktime[forecasting] is not installed. Install the `ml-forecast` extra."
            ) from exc
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        kwargs: dict[str, Any] = {"information_criterion": self.information_criterion}
        if self.sp:
            kwargs["sp"] = int(self.sp)
        if self.seasonal_periods:
            kwargs["sp"] = int(self.seasonal_periods)
        return SktimeForecaster(estimator=AutoETS(**kwargs))


@register("AutoARIMAForecastModel", kind="model")
class AutoARIMAForecastModel(_ForecasterModel):
    """Auto-ARIMA via sktime/pmdarima with stepwise stationarity selection."""

    def __init__(
        self,
        horizon: int | None = None,
        seasonal: bool = True,
        sp: int | None = None,
        max_p: int = 5,
        max_q: int = 5,
        max_d: int = 2,
        information_criterion: str = "aicc",
    ) -> None:
        super().__init__(horizon=horizon)
        self.seasonal = bool(seasonal)
        self.sp = sp
        self.max_p = int(max_p)
        self.max_q = int(max_q)
        self.max_d = int(max_d)
        self.information_criterion = str(information_criterion)

    def _build_forecaster(self) -> Any:
        try:
            from sktime.forecasting.arima import AutoARIMA
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "sktime[forecasting] (with pmdarima) is required. Install `ml-forecast`."
            ) from exc
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        kwargs: dict[str, Any] = {
            "seasonal": self.seasonal,
            "max_p": self.max_p,
            "max_q": self.max_q,
            "max_d": self.max_d,
            "information_criterion": self.information_criterion,
            "suppress_warnings": True,
        }
        if self.sp:
            kwargs["sp"] = int(self.sp)
        return SktimeForecaster(estimator=AutoARIMA(**kwargs))


@register("ThetaForecastModel", kind="model")
class ThetaForecastModel(_ForecasterModel):
    """Theta forecaster (Assimakopoulos & Nikolopoulos, 2000).

    A robust univariate baseline that often beats more complex models on
    seasonal financial series. Backed by sktime's ``ThetaForecaster``.
    """

    def __init__(
        self,
        horizon: int | None = None,
        sp: int | None = None,
        deseasonalize: bool = True,
    ) -> None:
        super().__init__(horizon=horizon)
        self.sp = sp
        self.deseasonalize = bool(deseasonalize)

    def _build_forecaster(self) -> Any:
        try:
            from sktime.forecasting.theta import ThetaForecaster
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "sktime[forecasting] is not installed. Install the `ml-forecast` extra."
            ) from exc
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        kwargs: dict[str, Any] = {"deseasonalize": self.deseasonalize}
        if self.sp:
            kwargs["sp"] = int(self.sp)
        return SktimeForecaster(estimator=ThetaForecaster(**kwargs))


@register("BatsTbatsForecastModel", kind="model")
class BatsTbatsForecastModel(_ForecasterModel):
    """BATS / TBATS — multi-seasonal exponential smoothing.

    Useful for series with multiple periodicities (e.g. intraday cycles
    overlaid with day-of-week or week-of-month effects).
    """

    def __init__(
        self,
        horizon: int | None = None,
        sp: int | list[int] | None = None,
        use_box_cox: bool | None = None,
        use_trend: bool | None = None,
        use_damped_trend: bool | None = None,
        use_arma_errors: bool | None = None,
        flavor: str = "tbats",
    ) -> None:
        super().__init__(horizon=horizon)
        self.sp = sp
        self.use_box_cox = use_box_cox
        self.use_trend = use_trend
        self.use_damped_trend = use_damped_trend
        self.use_arma_errors = use_arma_errors
        self.flavor = str(flavor).lower()

    def _build_forecaster(self) -> Any:
        try:
            if self.flavor == "bats":
                from sktime.forecasting.bats import BATS as _Forecaster
            else:
                from sktime.forecasting.tbats import TBATS as _Forecaster
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "sktime[forecasting] (with tbats) is required. Install `ml-forecast`."
            ) from exc
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        kwargs: dict[str, Any] = {}
        for key in ("use_box_cox", "use_trend", "use_damped_trend", "use_arma_errors"):
            value = getattr(self, key)
            if value is not None:
                kwargs[key] = value
        if self.sp is not None:
            kwargs["sp"] = self.sp
        return SktimeForecaster(estimator=_Forecaster(**kwargs))


__all__ = [
    "AutoARIMAForecastModel",
    "AutoETSForecastModel",
    "BatsTbatsForecastModel",
    "ProphetForecastModel",
    "SktimeForecastModel",
    "SktimeReductionForecastModel",
    "ThetaForecastModel",
]
