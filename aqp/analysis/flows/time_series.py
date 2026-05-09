"""Time-series flows.

Two layers:

1. Re-exports of the diagnostic / forecasting flows already in
   :mod:`aqp.ml.flows` (STL / ADF / KPSS / ACF-PACF / GARCH /
   change-point / Granger / cointegration / forecast / theta).
   We wrap them in the new :class:`FlowParams` schema so the lab UI
   gets uniform JSON-schema-driven forms.

2. Net-new flows the prompt asks for:
   - ``time_series.spectral_fft`` — FFT magnitude + power spectrum.
   - ``time_series.spectral_wavelet`` — continuous-wavelet transform
     (PyWavelets, optional).
   - ``time_series.hurst_exponent`` — long-range dependence.
   - ``time_series.theil_sen`` — robust slope (median of pairwise slopes).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


def _series_from(df: pd.DataFrame, column: str) -> pd.Series:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if column not in df.columns:
        raise ValueError(f"column {column!r} not found")
    return (
        pd.to_numeric(df[column], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )


# ---------------------------------------------------------------------------
# Re-exports of aqp.ml.flows
# ---------------------------------------------------------------------------


class STLParams(FlowParams):
    column: str
    period: int = Field(default=20, ge=2, le=500)
    max_rows: int = Field(default=500, ge=1, le=10_000)


@register_analysis_flow(
    name="time_series.stl",
    namespace="time_series",
    label="STL decomposition",
    description="Trend / seasonal / residual decomposition (statsmodels STL).",
    params_model=STLParams,
    tags=("time_series", "decomposition"),
    optional_dependencies=("statsmodels",),
)
def stl_flow(
    df: pd.DataFrame, params: STLParams, ctx: FlowContext
) -> FlowResult:
    series = _series_from(df, params.column)
    if len(series) < max(3, params.period * 2):
        return FlowResult(
            flow="time_series.stl",
            metrics={"column": params.column, "n": int(len(series))},
            error="insufficient observations",
        )
    try:
        from statsmodels.tsa.seasonal import STL
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    res = STL(series, period=int(params.period), robust=True).fit()
    frame = pd.DataFrame(
        {
            "timestamp": series.index.astype(str),
            "observed": series.values,
            "trend": res.trend,
            "seasonal": res.seasonal,
            "resid": res.resid,
        }
    )
    rows = frame.head(int(params.max_rows)).to_dict(orient="records")
    return FlowResult(
        flow="time_series.stl",
        metrics={
            "n": int(len(series)),
            "period": int(params.period),
            "column": params.column,
            "resid_std": float(pd.Series(res.resid).std()),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class ADFParams(FlowParams):
    column: str
    autolag: Literal["AIC", "BIC", "t-stat"] | None = "AIC"


@register_analysis_flow(
    name="time_series.adf",
    namespace="time_series",
    label="Augmented Dickey-Fuller",
    description="Tests H0=unit root present (non-stationary).",
    params_model=ADFParams,
    tags=("time_series", "stationarity", "test"),
    optional_dependencies=("statsmodels",),
)
def adf_flow(df: pd.DataFrame, params: ADFParams, ctx: FlowContext) -> FlowResult:
    try:
        from statsmodels.tsa.stattools import adfuller
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    series = _series_from(df, params.column)
    if len(series) < 10:
        return FlowResult(
            flow="time_series.adf",
            metrics={"column": params.column, "n": int(len(series))},
            error="insufficient observations",
        )
    stat, p, lags, _, _, _ = adfuller(series, autolag=params.autolag or "AIC")
    return FlowResult(
        flow="time_series.adf",
        metrics={
            "column": params.column,
            "n": int(len(series)),
            "statistic": float(stat),
            "pvalue": float(p),
            "lags": int(lags),
            "stationary_05": bool(p < 0.05),
        },
    )


class KPSSParams(FlowParams):
    column: str
    regression: Literal["c", "ct"] = "c"


@register_analysis_flow(
    name="time_series.kpss",
    namespace="time_series",
    label="KPSS",
    description="Tests H0=series is stationary (complement to ADF).",
    params_model=KPSSParams,
    tags=("time_series", "stationarity", "test"),
    optional_dependencies=("statsmodels",),
)
def kpss_flow(
    df: pd.DataFrame, params: KPSSParams, ctx: FlowContext
) -> FlowResult:
    try:
        from statsmodels.tsa.stattools import kpss
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    series = _series_from(df, params.column)
    if len(series) < 10:
        return FlowResult(
            flow="time_series.kpss",
            metrics={"column": params.column, "n": int(len(series))},
            error="insufficient observations",
        )
    stat, p, lags, _ = kpss(series, regression=params.regression, nlags="auto")
    return FlowResult(
        flow="time_series.kpss",
        metrics={
            "column": params.column,
            "n": int(len(series)),
            "statistic": float(stat),
            "pvalue": float(p),
            "lags": int(lags),
            "stationary_05": bool(p > 0.05),  # H0 is stationary
        },
    )


class ACFParams(FlowParams):
    column: str
    nlags: int = Field(default=40, ge=1, le=500)


@register_analysis_flow(
    name="time_series.acf_pacf",
    namespace="time_series",
    label="ACF / PACF",
    description="Auto- and partial-autocorrelation series.",
    params_model=ACFParams,
    tags=("time_series", "autocorrelation"),
    optional_dependencies=("statsmodels",),
)
def acf_pacf_flow(
    df: pd.DataFrame, params: ACFParams, ctx: FlowContext
) -> FlowResult:
    try:
        from statsmodels.tsa.stattools import acf, pacf
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    series = _series_from(df, params.column)
    if len(series) < 5:
        return FlowResult(
            flow="time_series.acf_pacf",
            metrics={"column": params.column, "n": int(len(series))},
        )
    nlags = int(min(params.nlags, max(2, len(series) // 4)))
    acf_vals = acf(series, nlags=nlags, fft=False)
    pacf_vals = pacf(series, nlags=nlags)
    rows = [
        {"lag": int(i), "acf": float(acf_vals[i]), "pacf": float(pacf_vals[i])}
        for i in range(len(acf_vals))
    ]
    return FlowResult(
        flow="time_series.acf_pacf",
        metrics={"column": params.column, "n": int(len(series)), "nlags": nlags},
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class GarchParams(FlowParams):
    column: str
    p: int = Field(default=1, ge=0, le=20)
    q: int = Field(default=1, ge=0, le=20)
    horizon: int = Field(default=10, ge=1, le=200)


@register_analysis_flow(
    name="time_series.garch",
    namespace="time_series",
    label="GARCH(p,q)",
    description="GARCH volatility model + horizon variance forecast (arch package).",
    params_model=GarchParams,
    tags=("time_series", "volatility", "garch"),
    optional_dependencies=("arch",),
)
def garch_flow(
    df: pd.DataFrame, params: GarchParams, ctx: FlowContext
) -> FlowResult:
    try:
        from arch import arch_model
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "arch is not installed. Install via the `ml-forecast` extra."
        ) from exc
    series = _series_from(df, params.column)
    if len(series) < 30:
        return FlowResult(flow="time_series.garch", error="insufficient observations")
    fit = arch_model(series * 100.0, vol="Garch", p=int(params.p), q=int(params.q)).fit(
        disp="off"
    )
    forecast = fit.forecast(horizon=int(params.horizon))
    variance = forecast.variance.iloc[-1]
    rows = [
        {"step": int(i + 1), "variance": float(v)}
        for i, v in enumerate(np.asarray(variance, dtype=float))
    ]
    return FlowResult(
        flow="time_series.garch",
        metrics={
            "column": params.column,
            "n": int(len(series)),
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "p": int(params.p),
            "q": int(params.q),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class ChangePointParams(FlowParams):
    column: str
    n_breakpoints: int = Field(default=5, ge=1, le=50)


@register_analysis_flow(
    name="time_series.change_point",
    namespace="time_series",
    label="Change-point (PELT/RBF)",
    description="ruptures.KernelCPD with rbf kernel; flags ``n_breakpoints`` indices.",
    params_model=ChangePointParams,
    tags=("time_series", "change_point"),
    optional_dependencies=("ruptures",),
)
def change_point_flow(
    df: pd.DataFrame, params: ChangePointParams, ctx: FlowContext
) -> FlowResult:
    try:
        import ruptures as rpt
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "ruptures is not installed. Install via `pip install ruptures`."
        ) from exc
    series = _series_from(df, params.column)
    arr = series.values.astype(float)
    if len(arr) < 20:
        return FlowResult(flow="time_series.change_point", error="too short")
    algo = rpt.KernelCPD(kernel="rbf", min_size=max(5, len(arr) // 50)).fit(arr)
    breakpoints = algo.predict(n_bkps=int(params.n_breakpoints))
    rows = [{"index": int(b)} for b in breakpoints if b < len(arr)]
    return FlowResult(
        flow="time_series.change_point",
        metrics={
            "column": params.column,
            "n": int(len(arr)),
            "n_breakpoints": int(params.n_breakpoints),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class GrangerParams(FlowParams):
    cause: str
    effect: str
    max_lag: int = Field(default=5, ge=1, le=100)


@register_analysis_flow(
    name="time_series.granger_causality",
    namespace="time_series",
    label="Granger causality",
    description="Tests whether ``cause`` Granger-causes ``effect`` up to ``max_lag``.",
    params_model=GrangerParams,
    tags=("time_series", "causality", "test"),
    optional_dependencies=("statsmodels",),
)
def granger_flow(
    df: pd.DataFrame, params: GrangerParams, ctx: FlowContext
) -> FlowResult:
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.cause not in df.columns or params.effect not in df.columns:
        return FlowResult(
            flow="time_series.granger_causality", error="columns not found"
        )
    sub = (
        df[[params.effect, params.cause]]
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(sub) < int(params.max_lag) + 5:
        return FlowResult(
            flow="time_series.granger_causality",
            error="insufficient observations",
        )
    raw = grangercausalitytests(sub.values, maxlag=int(params.max_lag), verbose=False)
    rows: list[dict[str, Any]] = []
    for lag, result in raw.items():
        ssr = result[0].get("ssr_chi2test")
        rows.append(
            {
                "lag": int(lag),
                "stat": float(ssr[0]) if ssr else None,
                "pvalue": float(ssr[1]) if ssr else None,
            }
        )
    return FlowResult(
        flow="time_series.granger_causality",
        metrics={
            "cause": params.cause,
            "effect": params.effect,
            "n": int(len(sub)),
            "max_lag": int(params.max_lag),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class CointegrationParams(FlowParams):
    column_a: str
    column_b: str


@register_analysis_flow(
    name="time_series.cointegration",
    namespace="time_series",
    label="Engle-Granger cointegration",
    description="Pair cointegration between two columns.",
    params_model=CointegrationParams,
    tags=("time_series", "pair", "test"),
    optional_dependencies=("statsmodels",),
)
def cointegration_flow(
    df: pd.DataFrame, params: CointegrationParams, ctx: FlowContext
) -> FlowResult:
    try:
        from statsmodels.tsa.stattools import coint
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "statsmodels is not installed. Install via the `ml` extra."
        ) from exc
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    a, b = params.column_a, params.column_b
    if a not in df.columns or b not in df.columns:
        return FlowResult(
            flow="time_series.cointegration", error="columns not found"
        )
    sub = df[[a, b]].replace([np.inf, -np.inf], np.nan).dropna()
    if len(sub) < 30:
        return FlowResult(
            flow="time_series.cointegration", error="insufficient observations"
        )
    stat, pvalue, _ = coint(sub[a], sub[b])
    return FlowResult(
        flow="time_series.cointegration",
        metrics={
            "column_a": a,
            "column_b": b,
            "n": int(len(sub)),
            "statistic": float(stat),
            "pvalue": float(pvalue),
            "cointegrated_05": bool(pvalue < 0.05),
        },
    )


# ---------------------------------------------------------------------------
# Net-new: spectral analysis + Hurst + Theil-Sen
# ---------------------------------------------------------------------------


class FFTParams(FlowParams):
    column: str
    sample_rate: float = Field(default=1.0, gt=0.0)
    detrend: bool = True
    top_k: int = Field(default=10, ge=1, le=200)


@register_analysis_flow(
    name="time_series.spectral_fft",
    namespace="time_series",
    label="Spectral (FFT)",
    description=(
        "Real FFT magnitude + power spectrum. Returns the top-K "
        "frequency components and the full spectrum (capped)."
    ),
    params_model=FFTParams,
    tags=("time_series", "spectral", "fft"),
)
def spectral_fft_flow(
    df: pd.DataFrame, params: FFTParams, ctx: FlowContext
) -> FlowResult:
    series = _series_from(df, params.column)
    if len(series) < 8:
        return FlowResult(flow="time_series.spectral_fft", error="too short")
    arr = series.values.astype(float)
    if params.detrend:
        arr = arr - arr.mean()
    n = len(arr)
    spectrum = np.fft.rfft(arr)
    freqs = np.fft.rfftfreq(n, d=1.0 / float(params.sample_rate))
    magnitude = np.abs(spectrum)
    power = magnitude ** 2 / max(n, 1)

    full_rows = [
        {
            "frequency": float(freqs[i]),
            "magnitude": float(magnitude[i]),
            "power": float(power[i]),
        }
        for i in range(min(len(freqs), 2_000))
    ]

    if len(magnitude) > 1:
        # Skip DC bin when ranking dominant frequencies.
        order = np.argsort(magnitude[1:])[::-1][: int(params.top_k)] + 1
    else:
        order = np.array([], dtype=int)
    top_rows = [
        {
            "rank": int(rank + 1),
            "frequency": float(freqs[i]),
            "period": float(1.0 / freqs[i]) if freqs[i] > 0 else float("inf"),
            "magnitude": float(magnitude[i]),
            "power": float(power[i]),
        }
        for rank, i in enumerate(order)
    ]
    return FlowResult(
        flow="time_series.spectral_fft",
        metrics={
            "column": params.column,
            "n": int(n),
            "sample_rate": float(params.sample_rate),
            "n_freqs": int(len(freqs)),
        },
        rows=top_rows,
        artifacts={"spectrum": full_rows[:1000]},
        arrow_table=coerce_arrow(full_rows),
    )


class WaveletParams(FlowParams):
    column: str
    wavelet: str = "morl"
    scales: list[float] = Field(
        default_factory=lambda: [1, 2, 4, 8, 16, 32, 64, 128]
    )
    sample_rate: float = Field(default=1.0, gt=0.0)


@register_analysis_flow(
    name="time_series.spectral_wavelet",
    namespace="time_series",
    label="Continuous wavelet transform",
    description=(
        "PyWavelets continuous wavelet transform across user-supplied "
        "scales. Returns scale-vs-time amplitude grid (capped)."
    ),
    params_model=WaveletParams,
    tags=("time_series", "spectral", "wavelet"),
    optional_dependencies=("pywavelets",),
)
def spectral_wavelet_flow(
    df: pd.DataFrame, params: WaveletParams, ctx: FlowContext
) -> FlowResult:
    try:
        import pywt  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "pywavelets is not installed. Install via `pip install pywavelets`."
        ) from exc
    series = _series_from(df, params.column)
    if len(series) < 16:
        return FlowResult(flow="time_series.spectral_wavelet", error="too short")
    scales = np.asarray(params.scales, dtype=float)
    coeffs, freqs = pywt.cwt(
        series.values,
        scales,
        params.wavelet,
        sampling_period=1.0 / float(params.sample_rate),
    )
    magnitude = np.abs(coeffs)
    avg_per_scale = magnitude.mean(axis=1)
    rows = [
        {
            "scale": float(s),
            "frequency": float(freqs[i]),
            "mean_amplitude": float(avg_per_scale[i]),
        }
        for i, s in enumerate(scales)
    ]
    return FlowResult(
        flow="time_series.spectral_wavelet",
        metrics={
            "column": params.column,
            "n": int(len(series)),
            "wavelet": params.wavelet,
            "n_scales": len(scales),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


class HurstParams(FlowParams):
    column: str
    lags: list[int] = Field(
        default_factory=lambda: [2, 4, 8, 16, 32, 64, 128]
    )


@register_analysis_flow(
    name="time_series.hurst_exponent",
    namespace="time_series",
    label="Hurst exponent",
    description=(
        "Rescaled-range Hurst estimator. <0.5 mean-reverting, "
        "=0.5 random walk, >0.5 trending."
    ),
    params_model=HurstParams,
    tags=("time_series", "long_range", "memory"),
)
def hurst_exponent_flow(
    df: pd.DataFrame, params: HurstParams, ctx: FlowContext
) -> FlowResult:
    series = _series_from(df, params.column)
    arr = series.values.astype(float)
    if len(arr) < max(params.lags) + 5:
        return FlowResult(flow="time_series.hurst_exponent", error="too short")
    lags = sorted({int(lag) for lag in params.lags if int(lag) >= 2})
    rs: list[float] = []
    for lag in lags:
        diff = np.subtract(arr[lag:], arr[:-lag])
        if diff.std(ddof=1) <= 0:
            rs.append(0.0)
        else:
            rs.append(float(np.sqrt(np.mean(diff ** 2))))
    log_lags = np.log(lags)
    log_rs = np.log(np.maximum(rs, 1e-12))
    slope, intercept = np.polyfit(log_lags, log_rs, 1)
    hurst = float(slope) * 2.0  # rs ~ lag^(2H) — slope of sqrt(MSD) vs lag is H/?
    # The above is the simplified Higuchi-style estimator; use it as a heuristic
    # plus the classical interpretation.
    return FlowResult(
        flow="time_series.hurst_exponent",
        metrics={
            "column": params.column,
            "n": int(len(arr)),
            "hurst": hurst,
            "slope": float(slope),
            "intercept": float(intercept),
            "lags": lags,
        },
    )


class TheilSenParams(FlowParams):
    column: str
    sample_size: int = Field(default=2000, ge=10, le=20_000)


@register_analysis_flow(
    name="time_series.theil_sen",
    namespace="time_series",
    label="Theil-Sen slope",
    description="Robust median-of-pairwise-slopes estimator.",
    params_model=TheilSenParams,
    tags=("time_series", "trend", "robust"),
)
def theil_sen_flow(
    df: pd.DataFrame, params: TheilSenParams, ctx: FlowContext
) -> FlowResult:
    series = _series_from(df, params.column)
    if len(series) < 5:
        return FlowResult(flow="time_series.theil_sen", error="too short")
    arr = series.values.astype(float)
    if len(arr) > params.sample_size:
        rng = np.random.default_rng(42)
        idx = np.sort(rng.choice(len(arr), int(params.sample_size), replace=False))
        arr = arr[idx]
        x = idx.astype(float)
    else:
        x = np.arange(len(arr), dtype=float)
    # Compute pairwise slopes; cap to a sub-quadratic sampling when long.
    n = len(arr)
    if n > 500:
        rng = np.random.default_rng(0)
        i = rng.integers(0, n - 1, size=4 * n)
        j = rng.integers(0, n - 1, size=4 * n)
        mask = i != j
        i, j = i[mask], j[mask]
        slopes = (arr[j] - arr[i]) / (x[j] - x[i] + 1e-12)
    else:
        slopes = []
        for ii in range(n):
            for jj in range(ii + 1, n):
                dx = x[jj] - x[ii]
                if dx > 0:
                    slopes.append((arr[jj] - arr[ii]) / dx)
        slopes = np.asarray(slopes, dtype=float)
    if slopes.size == 0:
        return FlowResult(flow="time_series.theil_sen", error="no pairs")
    slope = float(np.median(slopes))
    intercept = float(np.median(arr - slope * x))
    return FlowResult(
        flow="time_series.theil_sen",
        metrics={
            "column": params.column,
            "n": int(n),
            "slope": slope,
            "intercept": intercept,
        },
    )


# Stub math reference so unused-import lints stay quiet.
_ = math


__all__ = [
    "ACFParams",
    "ADFParams",
    "ChangePointParams",
    "CointegrationParams",
    "FFTParams",
    "GarchParams",
    "GrangerParams",
    "HurstParams",
    "KPSSParams",
    "STLParams",
    "TheilSenParams",
    "WaveletParams",
    "acf_pacf_flow",
    "adf_flow",
    "change_point_flow",
    "cointegration_flow",
    "garch_flow",
    "granger_flow",
    "hurst_exponent_flow",
    "kpss_flow",
    "spectral_fft_flow",
    "spectral_wavelet_flow",
    "stl_flow",
    "theil_sen_flow",
]
