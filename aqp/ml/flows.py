"""Lightweight synchronous ML flows for interactive workbenches."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import build_from_config
from aqp.ml.models._utils import prepare_panel, split_xy

logger = logging.getLogger(__name__)


@dataclass
class FlowResult:
    flow: str
    metrics: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LINEAR_ESTIMATORS = {"ridge", "lasso", "elasticnet", "linear", "bayesian_ridge"}


def run_linear_flow(
    dataset_cfg: dict[str, Any],
    *,
    estimator: str = "ridge",
    alpha: float = 1.0,
    l1_ratio: float = 0.5,
    segment: str = "test",
) -> FlowResult:
    from aqp.ml.models.linear import LinearModel

    estimator = str(estimator).lower()
    if estimator not in _LINEAR_ESTIMATORS:
        raise ValueError(
            f"Unknown linear estimator {estimator!r}. Choose from {sorted(_LINEAR_ESTIMATORS)}."
        )
    dataset = build_from_config(dataset_cfg)
    model_kwargs: dict[str, Any] = {"estimator": estimator}
    if estimator in {"ridge", "lasso"}:
        model_kwargs["alpha"] = float(alpha)
    elif estimator == "elasticnet":
        model_kwargs["alpha"] = float(alpha)
        model_kwargs["l1_ratio"] = float(l1_ratio)
    model = LinearModel(**model_kwargs)
    model.fit(dataset)
    pred = model.predict(dataset, segment=segment)
    metrics = {"n_predictions": int(len(pred))}
    try:
        raw = dataset.prepare(segment, col_set="label")
        label = raw.iloc[:, 0] if isinstance(raw, pd.DataFrame) else raw
        joined = pd.concat([pred.rename("pred"), label.rename("label")], axis=1).dropna()
        if not joined.empty:
            err = joined["pred"] - joined["label"]
            metrics["rmse"] = float(np.sqrt(np.mean(np.square(err))))
            metrics["mae"] = float(np.mean(np.abs(err)))
            metrics["ic"] = float(joined["pred"].corr(joined["label"], method="spearman"))
    except Exception:
        pass
    return FlowResult(
        flow="linear",
        metrics=metrics,
        rows=pred.rename("score").reset_index().head(100).to_dict(orient="records"),
        artifacts={
            "estimator": estimator,
            "coef": (
                getattr(model, "coef_", []).tolist()
                if getattr(model, "coef_", None) is not None
                else []
            ),
        },
    )


def run_decomposition_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    column: str | None = None,
    period: int = 20,
    max_rows: int = 500,
) -> FlowResult:
    try:
        from statsmodels.tsa.seasonal import STL
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc
    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    if column and column in features:
        values = X[:, features.index(column)]
        selected = column
    else:
        values = y
        selected = "label"
    series = pd.Series(values, index=panel.index).astype(float)
    if isinstance(series.index, pd.MultiIndex):
        series = series.groupby(level=0).mean()
    series = series.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
    if len(series) < max(3, period * 2):
        rows = pd.DataFrame({"timestamp": series.index.astype(str), "observed": series.values})
        return FlowResult(flow="decomposition", metrics={"n": int(len(series)), "column": selected}, rows=rows.head(max_rows).to_dict(orient="records"))
    res = STL(series, period=int(period), robust=True).fit()
    frame = pd.DataFrame(
        {
            "timestamp": series.index.astype(str),
            "observed": series.values,
            "trend": res.trend,
            "seasonal": res.seasonal,
            "resid": res.resid,
        }
    )
    return FlowResult(
        flow="decomposition",
        metrics={
            "n": int(len(series)),
            "period": int(period),
            "column": selected,
            "resid_std": float(pd.Series(res.resid).std()),
        },
        rows=frame.head(max_rows).to_dict(orient="records"),
    )


_FORECAST_BACKENDS = {"prophet", "sktime", "naive", "arima", "ets", "theta", "autoarima"}


def _series_from_dataset(
    dataset_cfg: dict[str, Any], segment: str
) -> pd.Series:
    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    _, y, _ = split_xy(panel)
    series = pd.Series(y, index=panel.index, name="label")
    if isinstance(series.index, pd.MultiIndex):
        series = series.groupby(level=0).mean()
    series.index = pd.to_datetime(series.index, errors="coerce")
    series = series[series.index.notna()].dropna()
    return series.sort_index()


def run_forecast_flow(
    dataset_cfg: dict[str, Any],
    *,
    backend: str = "prophet",
    horizon: int = 20,
    segment: str = "train",
    forecaster_kwargs: dict[str, Any] | None = None,
) -> FlowResult:
    backend = str(backend).lower()
    if backend not in _FORECAST_BACKENDS:
        raise ValueError(
            f"Unknown forecast backend {backend!r}. Choose from {sorted(_FORECAST_BACKENDS)}."
        )
    series = _series_from_dataset(dataset_cfg, segment)

    pred: pd.Series
    if backend in {"sktime", "naive"}:
        from aqp.ml.applications.forecaster.sktime_adapter import SktimeForecaster

        try:
            from sktime.forecasting.naive import NaiveForecaster
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "sktime is not installed. Install the `ml-forecast` extra."
            ) from exc
        strategy = (forecaster_kwargs or {}).get("strategy", "last")
        forecaster = SktimeForecaster(NaiveForecaster(strategy=strategy))
        forecaster.fit(series)
        pred = forecaster.predict(int(horizon))
    elif backend == "theta":
        from aqp.ml.adhoc.forecast import quick_theta

        pred = quick_theta(series, horizon=int(horizon)).forecast
    elif backend == "arima":
        from aqp.ml.adhoc.timeseries import quick_arima

        order = (forecaster_kwargs or {}).get("order", (1, 1, 1))
        pred = quick_arima(series, horizon=int(horizon), order=tuple(order)).forecast
    elif backend == "autoarima":
        try:
            from sktime.forecasting.arima import AutoARIMA
            from sktime.forecasting.base import ForecastingHorizon
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "sktime[forecasting] (with pmdarima) is required."
            ) from exc
        forecaster = AutoARIMA(
            seasonal=False,
            suppress_warnings=True,
            **(forecaster_kwargs or {}),
        )
        forecaster.fit(series)
        fh = ForecastingHorizon(list(range(1, int(horizon) + 1)), is_relative=True)
        pred = forecaster.predict(fh=fh)
    elif backend == "ets":
        from aqp.ml.adhoc.timeseries import quick_ets

        kwargs = forecaster_kwargs or {}
        pred = quick_ets(
            series,
            horizon=int(horizon),
            trend=kwargs.get("trend", "add"),
            seasonal=kwargs.get("seasonal"),
            seasonal_periods=kwargs.get("seasonal_periods"),
        ).forecast
    else:  # prophet
        from aqp.ml.applications.forecaster.prophet_adapter import ProphetForecaster

        forecaster = ProphetForecaster(**(forecaster_kwargs or {}))
        forecaster.fit(series)
        pred = forecaster.predict(int(horizon))

    if not isinstance(pred, pd.Series):
        pred = pd.Series(pred)
    frame = pred.rename("yhat").reset_index()
    frame.columns = ["timestamp", "yhat"]
    frame["timestamp"] = frame["timestamp"].astype(str)
    return FlowResult(
        flow="forecast",
        metrics={
            "horizon": int(horizon),
            "backend": backend,
            "n_train": int(len(series)),
        },
        rows=frame.to_dict(orient="records"),
    )


# ---------------------------------------------------------------------------
# Diagnostic / statistical flows added in the ML engine major expansion.
# Each is a thin wrapper around statsmodels / sklearn / arch / ruptures so
# the workbench can pivot between exploratory analyses without leaving the
# canvas.
# ---------------------------------------------------------------------------


def run_regression_diagnostics_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    max_features: int = 20,
) -> FlowResult:
    """Fit a quick OLS and return coefficients + residual diagnostics."""
    try:
        import statsmodels.api as sm
        from statsmodels.stats.stattools import durbin_watson
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X_arr, y, features = split_xy(panel)
    feats = features[: int(max_features)]
    X = pd.DataFrame(X_arr[:, : len(feats)], columns=feats).replace(
        [np.inf, -np.inf], np.nan
    )
    y_series = pd.Series(y, name="label").replace([np.inf, -np.inf], np.nan)
    joined = pd.concat([X, y_series], axis=1).dropna()
    if joined.empty:
        return FlowResult(
            flow="regression_diagnostics",
            metrics={"error": "no usable rows"},
        )
    Xc = sm.add_constant(joined[feats])
    fit = sm.OLS(joined["label"], Xc).fit()
    rows = [
        {
            "feature": feat,
            "coef": float(fit.params.get(feat, 0.0)),
            "stderr": float(fit.bse.get(feat, 0.0)),
            "tvalue": float(fit.tvalues.get(feat, 0.0)),
            "pvalue": float(fit.pvalues.get(feat, 1.0)),
        }
        for feat in feats
    ]
    return FlowResult(
        flow="regression_diagnostics",
        metrics={
            "rsquared": float(fit.rsquared),
            "rsquared_adj": float(fit.rsquared_adj),
            "f_pvalue": float(fit.f_pvalue),
            "durbin_watson": float(durbin_watson(fit.resid)),
            "n_obs": int(fit.nobs),
        },
        rows=rows,
    )


def run_unit_root_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    column: str | None = None,
    test: str = "adf",
) -> FlowResult:
    """ADF / KPSS / PP unit-root test on a single series."""
    try:
        from statsmodels.tsa.stattools import adfuller, kpss
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    if column and column in features:
        values = X[:, features.index(column)]
        selected = column
    else:
        values = y
        selected = "label"
    series = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < 10:
        return FlowResult(
            flow="unit_root",
            metrics={"column": selected, "n": int(len(series)), "error": "insufficient observations"},
        )
    out: dict[str, Any] = {"column": selected, "n": int(len(series))}
    test = test.lower()
    if test in {"adf", "all"}:
        stat, p, lags, _, _, _ = adfuller(series, autolag="AIC")
        out.update({"adf_stat": float(stat), "adf_pvalue": float(p), "adf_lags": int(lags)})
    if test in {"kpss", "all"}:
        try:
            stat, p, lags, _ = kpss(series, regression="c", nlags="auto")
            out.update({"kpss_stat": float(stat), "kpss_pvalue": float(p), "kpss_lags": int(lags)})
        except Exception:
            logger.debug("KPSS failed", exc_info=True)
    return FlowResult(flow="unit_root", metrics=out)


def run_acf_pacf_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    column: str | None = None,
    nlags: int = 40,
) -> FlowResult:
    """Auto-correlation / partial-autocorrelation analysis."""
    try:
        from statsmodels.tsa.stattools import acf, pacf
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    if column and column in features:
        values = X[:, features.index(column)]
        selected = column
    else:
        values = y
        selected = "label"
    series = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    nlags = int(min(nlags, max(2, len(series) // 4)))
    if len(series) < 5:
        return FlowResult(flow="acf_pacf", metrics={"column": selected, "n": int(len(series))})
    acf_vals = acf(series, nlags=nlags, fft=False)
    pacf_vals = pacf(series, nlags=nlags)
    rows = [
        {"lag": int(i), "acf": float(acf_vals[i]), "pacf": float(pacf_vals[i])}
        for i in range(len(acf_vals))
    ]
    return FlowResult(
        flow="acf_pacf",
        metrics={"column": selected, "n": int(len(series)), "nlags": nlags},
        rows=rows,
    )


def run_granger_causality_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    cause_column: str | None = None,
    effect_column: str | None = None,
    max_lag: int = 5,
) -> FlowResult:
    """Granger causality test between two columns."""
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    cols_df = pd.DataFrame(X, columns=features)
    cols_df["label"] = y
    if not cause_column or cause_column not in cols_df.columns:
        cause_column = features[0] if features else "label"
    if not effect_column or effect_column not in cols_df.columns:
        effect_column = "label"
    if cause_column == effect_column:
        return FlowResult(flow="granger_causality", metrics={"error": "cause == effect"})
    sub = cols_df[[effect_column, cause_column]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < int(max_lag) + 5:
        return FlowResult(
            flow="granger_causality",
            metrics={"error": "insufficient observations", "n": int(len(sub))},
        )
    raw = grangercausalitytests(sub.values, maxlag=int(max_lag), verbose=False)
    rows = []
    for lag, result in raw.items():
        ssr_chi2 = result[0].get("ssr_chi2test")
        rows.append(
            {
                "lag": int(lag),
                "stat": float(ssr_chi2[0]) if ssr_chi2 else None,
                "pvalue": float(ssr_chi2[1]) if ssr_chi2 else None,
            }
        )
    return FlowResult(
        flow="granger_causality",
        metrics={
            "cause": cause_column,
            "effect": effect_column,
            "n": int(len(sub)),
            "max_lag": int(max_lag),
        },
        rows=rows,
    )


def run_cointegration_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    columns: list[str] | None = None,
) -> FlowResult:
    """Engle-Granger cointegration test for a pair of columns."""
    try:
        from statsmodels.tsa.stattools import coint
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    cols_df = pd.DataFrame(X, columns=features)
    cols_df["label"] = y
    pair = list(columns or features[:2] if len(features) >= 2 else (features[0:1] + ["label"]))
    if len(pair) < 2:
        return FlowResult(flow="cointegration", metrics={"error": "need 2 columns"})
    a, b = pair[0], pair[1]
    sub = cols_df[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 30:
        return FlowResult(
            flow="cointegration", metrics={"error": "insufficient observations", "n": int(len(sub))}
        )
    stat, pvalue, _ = coint(sub[a], sub[b])
    return FlowResult(
        flow="cointegration",
        metrics={
            "column_a": a,
            "column_b": b,
            "n": int(len(sub)),
            "coint_stat": float(stat),
            "pvalue": float(pvalue),
        },
    )


def run_garch_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    column: str | None = None,
    p: int = 1,
    q: int = 1,
    horizon: int = 10,
) -> FlowResult:
    """GARCH(p, q) volatility model on a single series (via the arch package)."""
    try:
        from arch import arch_model
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "arch is not installed. Install via `pip install arch` (or the `ml-forecast` extra)."
        ) from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    if column and column in features:
        values = X[:, features.index(column)]
        selected = column
    else:
        values = y
        selected = "label"
    series = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < 30:
        return FlowResult(flow="garch", metrics={"error": "insufficient observations"})
    fit = arch_model(series * 100, vol="Garch", p=int(p), q=int(q)).fit(disp="off")
    forecast = fit.forecast(horizon=int(horizon))
    variance = forecast.variance.iloc[-1]
    rows = [
        {"step": int(i + 1), "variance": float(v)}
        for i, v in enumerate(np.asarray(variance, dtype=float))
    ]
    return FlowResult(
        flow="garch",
        metrics={
            "column": selected,
            "n": int(len(series)),
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "p": int(p),
            "q": int(q),
        },
        rows=rows,
    )


def run_change_point_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    column: str | None = None,
    n_breakpoints: int = 5,
) -> FlowResult:
    """Detect change points (ruptures.Pelt with rbf kernel)."""
    try:
        import ruptures as rpt
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "ruptures is not installed. Install via `pip install ruptures`."
        ) from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, y, features = split_xy(panel)
    if column and column in features:
        values = X[:, features.index(column)]
        selected = column
    else:
        values = y
        selected = "label"
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 20:
        return FlowResult(flow="change_point", metrics={"error": "insufficient observations"})
    algo = rpt.KernelCPD(kernel="rbf", min_size=max(5, len(arr) // 50)).fit(arr)
    breakpoints = algo.predict(n_bkps=int(n_breakpoints))
    return FlowResult(
        flow="change_point",
        metrics={"column": selected, "n": int(len(arr)), "n_breakpoints": int(n_breakpoints)},
        rows=[{"index": int(b)} for b in breakpoints if b < len(arr)],
    )


def run_clustering_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    backend: str = "kmeans",
    n_clusters: int = 4,
    eps: float = 0.5,
    min_samples: int = 5,
) -> FlowResult:
    """KMeans / DBSCAN / HDBSCAN clustering on the feature matrix."""
    try:
        from sklearn.cluster import DBSCAN, KMeans
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, _, features = split_xy(panel)
    arr = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    backend = str(backend).lower()
    if backend == "kmeans":
        labels = KMeans(n_clusters=int(n_clusters), n_init=10).fit_predict(arr)
    elif backend == "dbscan":
        labels = DBSCAN(eps=float(eps), min_samples=int(min_samples)).fit_predict(arr)
    elif backend == "hdbscan":
        try:
            import hdbscan as _h
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "hdbscan is not installed. Install via `pip install hdbscan`."
            ) from exc
        labels = _h.HDBSCAN(min_samples=int(min_samples)).fit_predict(arr)
    else:
        raise ValueError(f"Unknown clustering backend {backend!r}")
    unique, counts = np.unique(labels, return_counts=True)
    return FlowResult(
        flow="clustering",
        metrics={
            "backend": backend,
            "n_rows": int(len(arr)),
            "n_features": int(arr.shape[1]),
            "n_clusters": int(len([u for u in unique if u != -1])),
            "n_noise": int((labels == -1).sum()),
        },
        rows=[
            {"cluster": int(label), "count": int(count)}
            for label, count in zip(unique, counts, strict=False)
        ],
        artifacts={"label_sample": labels[:200].tolist()},
    )


def run_pca_summary_flow(
    dataset_cfg: dict[str, Any],
    *,
    segment: str = "train",
    n_components: int = 10,
) -> FlowResult:
    """PCA variance-explained + factor loadings."""
    try:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc

    dataset = build_from_config(dataset_cfg)
    panel = prepare_panel(dataset, segment)
    X, _, features = split_xy(panel)
    arr = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    scaled = StandardScaler().fit_transform(arr)
    n = int(min(n_components, scaled.shape[1]))
    pca = PCA(n_components=n).fit(scaled)
    rows = [
        {
            "component": int(i + 1),
            "variance_explained": float(pca.explained_variance_ratio_[i]),
            "cumulative_variance": float(np.cumsum(pca.explained_variance_ratio_)[i]),
            "top_features": [
                features[j]
                for j in np.argsort(np.abs(pca.components_[i]))[::-1][:5]
            ],
        }
        for i in range(n)
    ]
    return FlowResult(
        flow="pca_summary",
        metrics={
            "n_rows": int(len(arr)),
            "n_features": int(arr.shape[1]),
            "n_components": n,
            "total_explained": float(np.sum(pca.explained_variance_ratio_)),
        },
        rows=rows,
    )


def run_flow(flow: str, payload: dict[str, Any]) -> dict[str, Any]:
    dataset_cfg = payload.get("dataset_cfg") or {}
    flow = str(flow).lower()
    if flow == "linear":
        return run_linear_flow(
            dataset_cfg,
            estimator=payload.get("estimator", "ridge"),
            alpha=float(payload.get("alpha", 1.0)),
            l1_ratio=float(payload.get("l1_ratio", 0.5)),
            segment=payload.get("segment", "test"),
        ).to_dict()
    if flow == "decomposition":
        return run_decomposition_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            column=payload.get("column"),
            period=int(payload.get("period", 20)),
        ).to_dict()
    if flow == "forecast":
        return run_forecast_flow(
            dataset_cfg,
            backend=payload.get("backend", "prophet"),
            horizon=int(payload.get("horizon", 20)),
            segment=payload.get("segment", "train"),
            forecaster_kwargs=payload.get("forecaster_kwargs") or {},
        ).to_dict()
    if flow == "regression_diagnostics":
        return run_regression_diagnostics_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            max_features=int(payload.get("max_features", 20)),
        ).to_dict()
    if flow == "unit_root":
        return run_unit_root_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            column=payload.get("column"),
            test=payload.get("test", "all"),
        ).to_dict()
    if flow == "acf_pacf":
        return run_acf_pacf_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            column=payload.get("column"),
            nlags=int(payload.get("nlags", 40)),
        ).to_dict()
    if flow == "granger_causality":
        return run_granger_causality_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            cause_column=payload.get("cause_column"),
            effect_column=payload.get("effect_column"),
            max_lag=int(payload.get("max_lag", 5)),
        ).to_dict()
    if flow == "cointegration":
        return run_cointegration_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            columns=payload.get("columns") or None,
        ).to_dict()
    if flow == "garch":
        return run_garch_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            column=payload.get("column"),
            p=int(payload.get("p", 1)),
            q=int(payload.get("q", 1)),
            horizon=int(payload.get("horizon", 10)),
        ).to_dict()
    if flow == "change_point":
        return run_change_point_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            column=payload.get("column"),
            n_breakpoints=int(payload.get("n_breakpoints", 5)),
        ).to_dict()
    if flow == "clustering":
        return run_clustering_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            backend=payload.get("backend", "kmeans"),
            n_clusters=int(payload.get("n_clusters", 4)),
            eps=float(payload.get("eps", 0.5)),
            min_samples=int(payload.get("min_samples", 5)),
        ).to_dict()
    if flow == "pca_summary":
        return run_pca_summary_flow(
            dataset_cfg,
            segment=payload.get("segment", "train"),
            n_components=int(payload.get("n_components", 10)),
        ).to_dict()
    raise ValueError(f"Unknown ML flow {flow!r}")


def list_flows() -> list[dict[str, Any]]:
    """Return metadata for every registered flow.

    Used by ``GET /ml/flows`` (added in the ML expansion) and the webui
    workbench palette to render forms.
    """
    return [
        {
            "flow": "linear",
            "label": "Linear regression",
            "description": "Fit Ridge / Lasso / ElasticNet / BayesianRidge on the dataset.",
            "fields": [
                {"name": "estimator", "type": "select", "options": sorted(_LINEAR_ESTIMATORS)},
                {"name": "alpha", "type": "number", "default": 1.0},
                {"name": "l1_ratio", "type": "number", "default": 0.5},
                {"name": "segment", "type": "string", "default": "test"},
            ],
        },
        {
            "flow": "decomposition",
            "label": "STL decomposition",
            "description": "Trend / seasonal / residual via STL.",
            "fields": [
                {"name": "segment", "type": "string", "default": "train"},
                {"name": "column", "type": "string"},
                {"name": "period", "type": "integer", "default": 20},
            ],
        },
        {
            "flow": "forecast",
            "label": "Forecast",
            "description": "Prophet / sktime / ARIMA / ETS / Theta / AutoARIMA forecast.",
            "fields": [
                {"name": "backend", "type": "select", "options": sorted(_FORECAST_BACKENDS)},
                {"name": "horizon", "type": "integer", "default": 20},
                {"name": "segment", "type": "string", "default": "train"},
            ],
        },
        {
            "flow": "regression_diagnostics",
            "label": "OLS diagnostics",
            "description": "OLS coefficients, R^2, F-stat, Durbin-Watson.",
            "fields": [
                {"name": "segment", "type": "string", "default": "train"},
                {"name": "max_features", "type": "integer", "default": 20},
            ],
        },
        {
            "flow": "unit_root",
            "label": "Unit-root test",
            "description": "ADF / KPSS unit-root tests on a series.",
            "fields": [
                {"name": "column", "type": "string"},
                {"name": "test", "type": "select", "options": ["adf", "kpss", "all"]},
            ],
        },
        {
            "flow": "acf_pacf",
            "label": "ACF / PACF",
            "description": "Auto- and partial-autocorrelation series.",
            "fields": [
                {"name": "column", "type": "string"},
                {"name": "nlags", "type": "integer", "default": 40},
            ],
        },
        {
            "flow": "granger_causality",
            "label": "Granger causality",
            "description": "Test whether one series Granger-causes another.",
            "fields": [
                {"name": "cause_column", "type": "string"},
                {"name": "effect_column", "type": "string"},
                {"name": "max_lag", "type": "integer", "default": 5},
            ],
        },
        {
            "flow": "cointegration",
            "label": "Cointegration (Engle-Granger)",
            "description": "Test cointegration between two series.",
            "fields": [{"name": "columns", "type": "list", "default": []}],
        },
        {
            "flow": "garch",
            "label": "GARCH volatility",
            "description": "GARCH(p, q) volatility model and forecast.",
            "fields": [
                {"name": "column", "type": "string"},
                {"name": "p", "type": "integer", "default": 1},
                {"name": "q", "type": "integer", "default": 1},
                {"name": "horizon", "type": "integer", "default": 10},
            ],
        },
        {
            "flow": "change_point",
            "label": "Change-point detection",
            "description": "PELT / RBF kernel change-point detection.",
            "fields": [
                {"name": "column", "type": "string"},
                {"name": "n_breakpoints", "type": "integer", "default": 5},
            ],
        },
        {
            "flow": "clustering",
            "label": "Clustering",
            "description": "KMeans / DBSCAN / HDBSCAN on the feature matrix.",
            "fields": [
                {"name": "backend", "type": "select", "options": ["kmeans", "dbscan", "hdbscan"]},
                {"name": "n_clusters", "type": "integer", "default": 4},
            ],
        },
        {
            "flow": "pca_summary",
            "label": "PCA summary",
            "description": "Variance explained + top-feature loadings.",
            "fields": [{"name": "n_components", "type": "integer", "default": 10}],
        },
    ]


__all__ = [
    "FlowResult",
    "list_flows",
    "run_acf_pacf_flow",
    "run_change_point_flow",
    "run_clustering_flow",
    "run_cointegration_flow",
    "run_decomposition_flow",
    "run_flow",
    "run_forecast_flow",
    "run_garch_flow",
    "run_granger_causality_flow",
    "run_linear_flow",
    "run_pca_summary_flow",
    "run_regression_diagnostics_flow",
    "run_unit_root_flow",
]
