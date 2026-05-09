"""Distribution flows — descriptive stats, histogram, ECDF, Q-Q, Shapiro / JB / K-S.

Empirical financial returns deviate sharply from normality (heavy
tails + skewness). These flows quantify that explicitly so users
don't apply Gaussian-only models to leptokurtic series.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field
from scipy import stats as sci_stats

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _series_from(df: pd.DataFrame, column: str) -> pd.Series:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if column not in df.columns:
        raise ValueError(f"column {column!r} not found in dataframe")
    s = df[column]
    return (
        pd.to_numeric(s, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )


# ---------------------------------------------------------------------------
# Descriptive stats
# ---------------------------------------------------------------------------


class DescriptiveStatsParams(FlowParams):
    column: str
    quantiles: list[float] = Field(
        default_factory=lambda: [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    )


@register_analysis_flow(
    name="distribution.descriptive_stats",
    namespace="distribution",
    label="Descriptive stats",
    description=(
        "Mean / median / std / variance / skew / kurtosis / IQR / MAD + "
        "user-supplied quantiles. Foundation for distribution audits."
    ),
    params_model=DescriptiveStatsParams,
    tags=("distribution", "summary"),
)
def descriptive_stats_flow(
    df: pd.DataFrame, params: DescriptiveStatsParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if s.empty:
        return FlowResult(
            flow="distribution.descriptive_stats",
            metrics={"column": params.column, "n": 0},
            error="no observations",
        )
    mean = float(s.mean())
    median = float(s.median())
    std = float(s.std(ddof=1)) if len(s) > 1 else 0.0
    var = float(s.var(ddof=1)) if len(s) > 1 else 0.0
    skew = float(sci_stats.skew(s)) if len(s) > 2 else 0.0
    kurt = float(sci_stats.kurtosis(s, fisher=True)) if len(s) > 3 else 0.0
    q1 = float(s.quantile(0.25)) if len(s) else 0.0
    q3 = float(s.quantile(0.75)) if len(s) else 0.0
    iqr = q3 - q1
    mad = float((s - median).abs().mean()) if len(s) else 0.0
    rows = [
        {"quantile": float(q), "value": float(s.quantile(q))}
        for q in sorted(set(params.quantiles))
    ]
    return FlowResult(
        flow="distribution.descriptive_stats",
        metrics={
            "column": params.column,
            "n": int(len(s)),
            "mean": mean,
            "median": median,
            "std": std,
            "var": var,
            "min": float(s.min()),
            "max": float(s.max()),
            "skew": skew,
            "kurtosis": kurt,  # excess kurtosis
            "iqr": iqr,
            "mad": mad,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class HistogramParams(FlowParams):
    column: str
    bins: int = Field(default=50, ge=2, le=500)
    density: bool = False


@register_analysis_flow(
    name="distribution.histogram",
    namespace="distribution",
    label="Histogram",
    description="Equal-width-binned counts (or density). Includes left edge for plotting.",
    params_model=HistogramParams,
    tags=("distribution", "chart"),
    output_kind="chart",
)
def histogram_flow(
    df: pd.DataFrame, params: HistogramParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if s.empty:
        return FlowResult(
            flow="distribution.histogram",
            metrics={"column": params.column, "n": 0},
        )
    counts, edges = np.histogram(s.values, bins=int(params.bins), density=params.density)
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(counts):
        rows.append(
            {
                "bin_left": float(edges[i]),
                "bin_right": float(edges[i + 1]),
                "bin_mid": float(0.5 * (edges[i] + edges[i + 1])),
                "count": float(c),
            }
        )
    chart = {
        "data": [
            {
                "type": "bar",
                "x": [r["bin_mid"] for r in rows],
                "y": [r["count"] for r in rows],
                "name": params.column,
            }
        ],
        "layout": {
            "title": f"Histogram of {params.column}",
            "bargap": 0.05,
        },
    }
    return FlowResult(
        flow="distribution.histogram",
        metrics={
            "column": params.column,
            "n": int(len(s)),
            "bins": int(params.bins),
            "density": bool(params.density),
        },
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# ECDF
# ---------------------------------------------------------------------------


class ECDFParams(FlowParams):
    column: str
    max_points: int = Field(default=1000, ge=10, le=20_000)


@register_analysis_flow(
    name="distribution.ecdf",
    namespace="distribution",
    label="Empirical CDF",
    description="Sorted-value ECDF (uniformly down-sampled to max_points).",
    params_model=ECDFParams,
    tags=("distribution", "chart"),
    output_kind="chart",
)
def ecdf_flow(
    df: pd.DataFrame, params: ECDFParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if s.empty:
        return FlowResult(flow="distribution.ecdf", metrics={"n": 0})
    arr = np.sort(s.values)
    n = len(arr)
    p = np.arange(1, n + 1) / n
    if n > params.max_points:
        idx = np.linspace(0, n - 1, params.max_points).astype(int)
        arr = arr[idx]
        p = p[idx]
    rows = [{"x": float(x), "ecdf": float(prob)} for x, prob in zip(arr, p, strict=False)]
    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "x": [r["x"] for r in rows],
                "y": [r["ecdf"] for r in rows],
                "name": f"ECDF({params.column})",
            }
        ],
        "layout": {"title": f"ECDF of {params.column}"},
    }
    return FlowResult(
        flow="distribution.ecdf",
        metrics={"n": int(n), "n_points": len(rows)},
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Q-Q plot points (vs normal)
# ---------------------------------------------------------------------------


class QQParams(FlowParams):
    column: str
    distribution: Literal["norm", "t", "uniform", "expon"] = "norm"
    sample_size: int = Field(default=2000, ge=10, le=20_000)


@register_analysis_flow(
    name="distribution.qq_plot_points",
    namespace="distribution",
    label="Q-Q plot points",
    description=(
        "Quantile-quantile plot points against a reference distribution "
        "(normal by default). Slope ~ scale, intercept ~ location."
    ),
    params_model=QQParams,
    tags=("distribution", "chart"),
    output_kind="chart",
)
def qq_plot_flow(
    df: pd.DataFrame, params: QQParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if s.empty:
        return FlowResult(flow="distribution.qq_plot_points", metrics={"n": 0})
    sample = s.values
    if len(sample) > params.sample_size:
        sample = np.random.default_rng(42).choice(sample, params.sample_size, replace=False)
    sample = np.sort(sample)
    n = len(sample)
    qs = (np.arange(1, n + 1) - 0.5) / n
    dist = getattr(sci_stats, params.distribution)
    if params.distribution == "t":
        theoretical = dist.ppf(qs, df=8)
    else:
        theoretical = dist.ppf(qs)
    rows = [
        {"theoretical": float(t), "sample": float(x)}
        for t, x in zip(theoretical, sample, strict=False)
    ]
    if n > 2:
        slope, intercept = np.polyfit(theoretical, sample, 1)
    else:
        slope, intercept = 1.0, 0.0
    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "markers",
                "x": [r["theoretical"] for r in rows],
                "y": [r["sample"] for r in rows],
                "name": "Q-Q",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "x": [float(theoretical[0]), float(theoretical[-1])],
                "y": [
                    float(slope * theoretical[0] + intercept),
                    float(slope * theoretical[-1] + intercept),
                ],
                "name": "fit",
            },
        ],
        "layout": {
            "title": f"Q-Q vs {params.distribution} for {params.column}",
            "xaxis": {"title": "theoretical"},
            "yaxis": {"title": "sample"},
        },
    }
    return FlowResult(
        flow="distribution.qq_plot_points",
        metrics={
            "column": params.column,
            "n": int(n),
            "slope": float(slope),
            "intercept": float(intercept),
            "distribution": params.distribution,
        },
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Shapiro-Wilk
# ---------------------------------------------------------------------------


class ShapiroParams(FlowParams):
    column: str
    sample_size: int = Field(default=5000, ge=10, le=5000)


@register_analysis_flow(
    name="distribution.shapiro_wilk",
    namespace="distribution",
    label="Shapiro-Wilk normality",
    description=(
        "Tests H0=column is normally distributed. Rejects H0 when "
        "p < 0.05. Capped at 5000 samples (scipy hard limit)."
    ),
    params_model=ShapiroParams,
    tags=("distribution", "normality", "test"),
)
def shapiro_wilk_flow(
    df: pd.DataFrame, params: ShapiroParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if len(s) < 3:
        return FlowResult(
            flow="distribution.shapiro_wilk",
            metrics={"column": params.column, "n": int(len(s)), "error": "n<3"},
        )
    sample = s.values
    if len(sample) > int(params.sample_size):
        sample = np.random.default_rng(42).choice(
            sample, int(params.sample_size), replace=False
        )
    stat, p_value = sci_stats.shapiro(sample)
    return FlowResult(
        flow="distribution.shapiro_wilk",
        metrics={
            "column": params.column,
            "n": int(len(sample)),
            "statistic": float(stat),
            "pvalue": float(p_value),
            "is_normal_05": bool(p_value > 0.05),
        },
    )


# ---------------------------------------------------------------------------
# Jarque-Bera
# ---------------------------------------------------------------------------


class JarqueBeraParams(FlowParams):
    column: str


@register_analysis_flow(
    name="distribution.jarque_bera",
    namespace="distribution",
    label="Jarque-Bera normality",
    description=(
        "Skewness + kurtosis goodness-of-fit test for normality. "
        "Higher statistic = stronger rejection."
    ),
    params_model=JarqueBeraParams,
    tags=("distribution", "normality", "test"),
)
def jarque_bera_flow(
    df: pd.DataFrame, params: JarqueBeraParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if len(s) < 3:
        return FlowResult(
            flow="distribution.jarque_bera",
            metrics={"column": params.column, "n": int(len(s)), "error": "n<3"},
        )
    stat, p_value = sci_stats.jarque_bera(s.values)
    return FlowResult(
        flow="distribution.jarque_bera",
        metrics={
            "column": params.column,
            "n": int(len(s)),
            "statistic": float(stat),
            "pvalue": float(p_value),
            "is_normal_05": bool(p_value > 0.05),
            "skew": float(sci_stats.skew(s)),
            "kurtosis": float(sci_stats.kurtosis(s, fisher=True)),
        },
    )


# ---------------------------------------------------------------------------
# Kolmogorov-Smirnov (one-sample, vs reference distribution)
# ---------------------------------------------------------------------------


class KSParams(FlowParams):
    column: str
    distribution: Literal["norm", "t", "uniform", "expon", "lognorm"] = "norm"
    standardize: bool = True


@register_analysis_flow(
    name="distribution.kolmogorov_smirnov",
    namespace="distribution",
    label="Kolmogorov-Smirnov",
    description=(
        "Non-parametric K-S goodness-of-fit against a reference "
        "distribution. Standardises by default for normal vs uniform tests."
    ),
    params_model=KSParams,
    tags=("distribution", "goodness_of_fit", "test"),
)
def ks_flow(
    df: pd.DataFrame, params: KSParams, ctx: FlowContext
) -> FlowResult:
    s = _series_from(df, params.column)
    if len(s) < 5:
        return FlowResult(
            flow="distribution.kolmogorov_smirnov",
            metrics={"column": params.column, "n": int(len(s)), "error": "n<5"},
        )
    arr = s.values.astype(float)
    if params.standardize and arr.std(ddof=1) > 0:
        arr = (arr - arr.mean()) / arr.std(ddof=1)
    if params.distribution == "t":
        stat, p_value = sci_stats.kstest(arr, "t", args=(8,))
    elif params.distribution == "lognorm":
        stat, p_value = sci_stats.kstest(arr, "lognorm", args=(1.0,))
    else:
        stat, p_value = sci_stats.kstest(arr, params.distribution)
    return FlowResult(
        flow="distribution.kolmogorov_smirnov",
        metrics={
            "column": params.column,
            "n": int(len(arr)),
            "distribution": params.distribution,
            "standardize": bool(params.standardize),
            "statistic": float(stat),
            "pvalue": float(p_value),
            "fits_05": bool(p_value > 0.05),
        },
    )


# Silence "imported but unused" for re-exported math helper.
_ = math


__all__ = [
    "DescriptiveStatsParams",
    "ECDFParams",
    "HistogramParams",
    "JarqueBeraParams",
    "KSParams",
    "QQParams",
    "ShapiroParams",
    "descriptive_stats_flow",
    "ecdf_flow",
    "histogram_flow",
    "jarque_bera_flow",
    "ks_flow",
    "qq_plot_flow",
    "shapiro_wilk_flow",
]
