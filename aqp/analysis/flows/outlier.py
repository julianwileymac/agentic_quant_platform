"""Outlier-detection flows.

Catalogue:

- ``outlier.zscore`` — robust z-score thresholding.
- ``outlier.iqr`` — Tukey IQR fences.
- ``outlier.iforest`` — sklearn :class:`IsolationForest`.
- ``outlier.dbscan`` — density-based clustering of features (``-1`` = noise).
- ``outlier.lof`` — sklearn :class:`LocalOutlierFactor`.
- ``outlier.ecod`` — PyOD ECOD (falls back to z-score when unavailable).
- ``outlier.pulse_vs_step`` — distinguish a transient *pulse* (one-off
  outlier returning to trend) from a *step* (permanent level shift),
  per the prompt's pulse / step taxonomy.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


def _column_array(df: pd.DataFrame, column: str) -> np.ndarray:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if column not in df.columns:
        raise ValueError(f"column {column!r} not found")
    arr = pd.to_numeric(df[column], errors="coerce").values.astype(float)
    return arr


def _feature_matrix(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if columns:
        cols = [c for c in columns if c in df.columns]
    else:
        cols = list(df.select_dtypes(include="number").columns)
    if not cols:
        raise ValueError("no numeric columns available for outlier detection")
    arr = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


# ---------------------------------------------------------------------------
# Z-score
# ---------------------------------------------------------------------------


class ZScoreParams(FlowParams):
    column: str
    threshold: float = Field(default=3.0, ge=1.0, le=10.0)
    robust: bool = Field(default=True, description="Use median / MAD instead of mean / std")


@register_analysis_flow(
    name="outlier.zscore",
    namespace="outlier",
    label="Z-score outliers",
    description="Robust (median/MAD) or classical (mean/std) z-score thresholding.",
    params_model=ZScoreParams,
    tags=("outlier", "univariate"),
)
def zscore_flow(
    df: pd.DataFrame, params: ZScoreParams, ctx: FlowContext
) -> FlowResult:
    arr = _column_array(df, params.column)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return FlowResult(flow="outlier.zscore", metrics={"n": 0})
    if params.robust:
        center = float(np.median(finite))
        scale = float(np.median(np.abs(finite - center))) * 1.4826
    else:
        center = float(finite.mean())
        scale = float(finite.std(ddof=1))
    if scale == 0:
        scale = 1e-12
    z = (arr - center) / scale
    flagged = np.where(np.abs(z) > float(params.threshold))[0]
    rows = [
        {
            "index": int(i),
            "value": float(arr[i]),
            "zscore": float(z[i]),
        }
        for i in flagged[:500]
    ]
    return FlowResult(
        flow="outlier.zscore",
        metrics={
            "column": params.column,
            "n": int(len(arr)),
            "n_outliers": int(len(flagged)),
            "fraction": float(len(flagged)) / len(arr) if len(arr) else 0.0,
            "center": center,
            "scale": scale,
            "robust": bool(params.robust),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# IQR (Tukey)
# ---------------------------------------------------------------------------


class IQRParams(FlowParams):
    column: str
    k: float = Field(default=1.5, ge=0.5, le=10.0)


@register_analysis_flow(
    name="outlier.iqr",
    namespace="outlier",
    label="Tukey IQR fences",
    description="Flag points outside [Q1 - k*IQR, Q3 + k*IQR].",
    params_model=IQRParams,
    tags=("outlier", "univariate"),
)
def iqr_flow(
    df: pd.DataFrame, params: IQRParams, ctx: FlowContext
) -> FlowResult:
    arr = _column_array(df, params.column)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return FlowResult(flow="outlier.iqr", metrics={"n": 0})
    q1 = float(np.quantile(finite, 0.25))
    q3 = float(np.quantile(finite, 0.75))
    iqr = q3 - q1
    lower = q1 - params.k * iqr
    upper = q3 + params.k * iqr
    flagged = np.where((arr < lower) | (arr > upper))[0]
    rows = [
        {"index": int(i), "value": float(arr[i])} for i in flagged[:500]
    ]
    return FlowResult(
        flow="outlier.iqr",
        metrics={
            "column": params.column,
            "n": int(len(arr)),
            "n_outliers": int(len(flagged)),
            "lower": lower,
            "upper": upper,
            "iqr": iqr,
            "q1": q1,
            "q3": q3,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Isolation Forest
# ---------------------------------------------------------------------------


class IForestParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    contamination: float = Field(default=0.05, ge=0.001, le=0.5)
    n_estimators: int = Field(default=100, ge=10, le=2000)
    random_state: int | None = 42


@register_analysis_flow(
    name="outlier.iforest",
    namespace="outlier",
    label="Isolation Forest",
    description="sklearn IsolationForest over the selected feature matrix.",
    params_model=IForestParams,
    tags=("outlier", "multivariate", "tree"),
    optional_dependencies=("scikit-learn",),
)
def iforest_flow(
    df: pd.DataFrame, params: IForestParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.ensemble import IsolationForest
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    arr = _feature_matrix(df, params.columns)
    model = IsolationForest(
        n_estimators=int(params.n_estimators),
        contamination=float(params.contamination),
        random_state=params.random_state,
    )
    labels = model.fit_predict(arr)  # 1 = inlier, -1 = outlier
    scores = model.decision_function(arr)
    flagged = np.where(labels == -1)[0]
    rows = [
        {"index": int(i), "score": float(scores[i])} for i in flagged[:500]
    ]
    return FlowResult(
        flow="outlier.iforest",
        metrics={
            "n_rows": int(arr.shape[0]),
            "n_features": int(arr.shape[1]),
            "n_outliers": int(len(flagged)),
            "fraction": float(len(flagged)) / max(arr.shape[0], 1),
            "contamination": float(params.contamination),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# DBSCAN
# ---------------------------------------------------------------------------


class DBSCANParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    eps: float = Field(default=0.5, ge=1e-3, le=1e6)
    min_samples: int = Field(default=5, ge=2, le=1000)


@register_analysis_flow(
    name="outlier.dbscan",
    namespace="outlier",
    label="DBSCAN",
    description="Density-based outliers (label = -1 means noise / outlier).",
    params_model=DBSCANParams,
    tags=("outlier", "multivariate", "density"),
    optional_dependencies=("scikit-learn",),
)
def dbscan_flow(
    df: pd.DataFrame, params: DBSCANParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.cluster import DBSCAN
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    arr = _feature_matrix(df, params.columns)
    model = DBSCAN(eps=float(params.eps), min_samples=int(params.min_samples))
    labels = model.fit_predict(arr)
    flagged = np.where(labels == -1)[0]
    rows = [{"index": int(i), "cluster": int(labels[i])} for i in flagged[:500]]
    return FlowResult(
        flow="outlier.dbscan",
        metrics={
            "n_rows": int(arr.shape[0]),
            "n_features": int(arr.shape[1]),
            "n_clusters": int(len(set(labels)) - (1 if -1 in labels else 0)),
            "n_outliers": int(len(flagged)),
            "fraction": float(len(flagged)) / max(arr.shape[0], 1),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Local Outlier Factor
# ---------------------------------------------------------------------------


class LOFParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    n_neighbors: int = Field(default=20, ge=2, le=500)
    contamination: float = Field(default=0.05, ge=0.001, le=0.5)


@register_analysis_flow(
    name="outlier.lof",
    namespace="outlier",
    label="Local Outlier Factor",
    description="sklearn LocalOutlierFactor with novelty=False (fit_predict).",
    params_model=LOFParams,
    tags=("outlier", "multivariate", "density"),
    optional_dependencies=("scikit-learn",),
)
def lof_flow(
    df: pd.DataFrame, params: LOFParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.neighbors import LocalOutlierFactor
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    arr = _feature_matrix(df, params.columns)
    n_neighbors = int(min(params.n_neighbors, max(2, arr.shape[0] - 1)))
    model = LocalOutlierFactor(
        n_neighbors=n_neighbors,
        contamination=float(params.contamination),
    )
    labels = model.fit_predict(arr)
    scores = -model.negative_outlier_factor_
    flagged = np.where(labels == -1)[0]
    rows = [
        {"index": int(i), "score": float(scores[i])} for i in flagged[:500]
    ]
    return FlowResult(
        flow="outlier.lof",
        metrics={
            "n_rows": int(arr.shape[0]),
            "n_features": int(arr.shape[1]),
            "n_outliers": int(len(flagged)),
            "n_neighbors": int(n_neighbors),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# ECOD (PyOD) — graceful fallback to z-score
# ---------------------------------------------------------------------------


class ECODParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    contamination: float = Field(default=0.05, ge=0.001, le=0.5)


@register_analysis_flow(
    name="outlier.ecod",
    namespace="outlier",
    label="ECOD (PyOD)",
    description=(
        "Empirical Cumulative-distribution-based Outlier Detection. "
        "Falls back to a global z-score when PyOD is unavailable."
    ),
    params_model=ECODParams,
    tags=("outlier", "multivariate", "ecdf"),
    optional_dependencies=("pyod",),
)
def ecod_flow(
    df: pd.DataFrame, params: ECODParams, ctx: FlowContext
) -> FlowResult:
    arr = _feature_matrix(df, params.columns)
    backend = "ecod"
    try:
        from pyod.models.ecod import ECOD  # type: ignore[import-not-found]

        model = ECOD(contamination=float(params.contamination))
        model.fit(arr)
        labels = model.labels_
        scores = model.decision_scores_
    except Exception as exc:  # pragma: no cover - optional dep
        logger.warning("PyOD unavailable (%s); falling back to z-score outlier.", exc)
        backend = "zscore_fallback"
        center = arr.mean(axis=0)
        scale = arr.std(axis=0, ddof=1) + 1e-12
        z = np.linalg.norm((arr - center) / scale, axis=1)
        thresh = float(np.quantile(z, 1.0 - params.contamination))
        labels = (z > thresh).astype(int)
        scores = z
    flagged = np.where(np.asarray(labels) == 1)[0]
    rows = [
        {"index": int(i), "score": float(scores[i])} for i in flagged[:500]
    ]
    return FlowResult(
        flow="outlier.ecod",
        metrics={
            "n_rows": int(arr.shape[0]),
            "n_features": int(arr.shape[1]),
            "n_outliers": int(len(flagged)),
            "backend": backend,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Pulse vs Step
# ---------------------------------------------------------------------------


class PulseStepParams(FlowParams):
    column: str
    window: int = Field(default=10, ge=2, le=200)
    z_threshold: float = Field(default=3.0, ge=1.0, le=10.0)
    persistence_window: int = Field(
        default=5,
        ge=1,
        le=200,
        description="Steps to look ahead when classifying pulse vs step.",
    )


@register_analysis_flow(
    name="outlier.pulse_vs_step",
    namespace="outlier",
    label="Pulse vs Step",
    description=(
        "Differentiate a transient pulse (single anomalous bar that "
        "reverts) from a step (permanent level shift). Useful for "
        "knowing whether to clip a value or split a series."
    ),
    params_model=PulseStepParams,
    tags=("outlier", "univariate", "time_series"),
)
def pulse_vs_step_flow(
    df: pd.DataFrame, params: PulseStepParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.column not in df.columns:
        raise ValueError(f"column {params.column!r} not found")
    arr = pd.to_numeric(df[params.column], errors="coerce").values.astype(float)
    n = len(arr)
    if n < params.window * 2:
        return FlowResult(
            flow="outlier.pulse_vs_step",
            metrics={"column": params.column, "n": int(n), "error": "too short"},
        )
    rolling_mean = pd.Series(arr).rolling(int(params.window), min_periods=1).mean()
    rolling_std = pd.Series(arr).rolling(int(params.window), min_periods=2).std()
    rolling_std = rolling_std.replace(0.0, np.nan).fillna(method="bfill").fillna(1e-9)
    z = (arr - rolling_mean) / rolling_std
    flagged = np.where(np.abs(z) > float(params.z_threshold))[0]
    rows: list[dict[str, Any]] = []
    pulse_count = 0
    step_count = 0
    persist = int(params.persistence_window)
    for i in flagged:
        end = min(int(i + persist), n - 1)
        if end <= int(i):
            continue
        pre_mean = float(np.nanmean(arr[max(0, int(i) - persist) : int(i)]) or 0.0)
        post_mean = float(np.nanmean(arr[int(i) + 1 : end + 1]) or 0.0)
        delta = post_mean - pre_mean
        local_scale = float(rolling_std.iloc[int(i)]) or 1e-9
        is_step = abs(delta) > 0.5 * local_scale
        kind: Literal["pulse", "step"] = "step" if is_step else "pulse"
        if kind == "pulse":
            pulse_count += 1
        else:
            step_count += 1
        rows.append(
            {
                "index": int(i),
                "value": float(arr[int(i)]),
                "zscore": float(z[int(i)]),
                "kind": kind,
                "pre_mean": pre_mean,
                "post_mean": post_mean,
                "delta": float(delta),
            }
        )
    return FlowResult(
        flow="outlier.pulse_vs_step",
        metrics={
            "column": params.column,
            "n": int(n),
            "n_outliers": int(len(rows)),
            "n_pulse": int(pulse_count),
            "n_step": int(step_count),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


__all__ = [
    "DBSCANParams",
    "ECODParams",
    "IForestParams",
    "IQRParams",
    "LOFParams",
    "PulseStepParams",
    "ZScoreParams",
    "dbscan_flow",
    "ecod_flow",
    "iforest_flow",
    "iqr_flow",
    "lof_flow",
    "pulse_vs_step_flow",
    "zscore_flow",
]
