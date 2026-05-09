"""Missing-value imputation flows.

Catalogue:

- ``imputation.ffill_bfill`` — forward / backward fill (price-friendly).
- ``imputation.linear`` — linear interpolation.
- ``imputation.spline`` — cubic spline interpolation (pandas).
- ``imputation.knn`` — sklearn :class:`KNNImputer` (multi-column).
- ``imputation.mice`` — sklearn :class:`IterativeImputer` (MICE).

Each flow returns the imputed sample plus a small audit (rows
imputed per column, total cells filled). The bulk Arrow output is
the imputed dataframe, so the runtime persists it to
``aqp_gold_analysis_imputation`` for downstream consumption.
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


def _pick_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if columns:
        return [c for c in columns if c in df.columns]
    return list(df.select_dtypes(include="number").columns)


def _audit(before: pd.DataFrame, after: pd.DataFrame) -> dict[str, Any]:
    audit: dict[str, Any] = {}
    total_filled = 0
    per_column: dict[str, int] = {}
    for col in before.columns:
        if col not in after.columns:
            continue
        delta = int(before[col].isna().sum()) - int(after[col].isna().sum())
        if delta:
            per_column[col] = delta
            total_filled += delta
    audit["total_filled"] = int(total_filled)
    audit["per_column"] = per_column
    return audit


def _truncate_rows(df: pd.DataFrame, limit: int = 200) -> list[dict[str, Any]]:
    if df.empty:
        return []
    sample = df.head(limit).copy()
    for col in sample.columns:
        if sample[col].dtype.kind not in ("i", "f"):
            sample[col] = sample[col].astype(str)
    return sample.to_dict(orient="records")


# ---------------------------------------------------------------------------
# ffill / bfill
# ---------------------------------------------------------------------------


class FfillBfillParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    method: Literal["ffill", "bfill", "ffill_then_bfill"] = "ffill_then_bfill"
    limit: int | None = None


@register_analysis_flow(
    name="imputation.ffill_bfill",
    namespace="imputation",
    label="Forward / backward fill",
    description=(
        "Fill NaNs with the most recent value (ffill) or the next "
        "value (bfill). Default is ffill_then_bfill — common for "
        "intra-day price gaps."
    ),
    params_model=FfillBfillParams,
    tags=("imputation", "time_series"),
)
def ffill_bfill_flow(
    df: pd.DataFrame, params: FfillBfillParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = _pick_columns(df, params.columns)
    out = df.copy()
    limit = int(params.limit) if params.limit else None
    if params.method == "ffill":
        out[cols] = out[cols].ffill(limit=limit)
    elif params.method == "bfill":
        out[cols] = out[cols].bfill(limit=limit)
    else:
        out[cols] = out[cols].ffill(limit=limit).bfill(limit=limit)
    audit = _audit(df[cols], out[cols])
    rows = _truncate_rows(out)
    return FlowResult(
        flow="imputation.ffill_bfill",
        metrics={
            "method": params.method,
            "n_rows": int(len(out)),
            "n_columns": len(cols),
            **audit,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# linear interpolation
# ---------------------------------------------------------------------------


class LinearInterpParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    limit: int | None = None
    limit_direction: Literal["forward", "backward", "both"] = "both"


@register_analysis_flow(
    name="imputation.linear",
    namespace="imputation",
    label="Linear interpolation",
    description="Time-aware linear interpolation via pandas (axis=0).",
    params_model=LinearInterpParams,
    tags=("imputation", "time_series", "interpolation"),
)
def linear_interp_flow(
    df: pd.DataFrame, params: LinearInterpParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = _pick_columns(df, params.columns)
    out = df.copy()
    out[cols] = out[cols].interpolate(
        method="linear",
        limit=int(params.limit) if params.limit else None,
        limit_direction=params.limit_direction,
    )
    audit = _audit(df[cols], out[cols])
    rows = _truncate_rows(out)
    return FlowResult(
        flow="imputation.linear",
        metrics={
            "n_rows": int(len(out)),
            "n_columns": len(cols),
            **audit,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Cubic spline
# ---------------------------------------------------------------------------


class SplineParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    order: int = Field(default=3, ge=1, le=5)


@register_analysis_flow(
    name="imputation.spline",
    namespace="imputation",
    label="Cubic-spline interpolation",
    description="pandas spline interpolation (order 3 by default).",
    params_model=SplineParams,
    tags=("imputation", "time_series", "interpolation"),
    optional_dependencies=("scipy",),
)
def spline_interp_flow(
    df: pd.DataFrame, params: SplineParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = _pick_columns(df, params.columns)
    out = df.copy()
    try:
        out[cols] = out[cols].interpolate(method="spline", order=int(params.order))
    except Exception as exc:  # noqa: BLE001
        logger.warning("spline interpolation failed (%s); falling back to linear", exc)
        out[cols] = out[cols].interpolate(method="linear")
    audit = _audit(df[cols], out[cols])
    rows = _truncate_rows(out)
    return FlowResult(
        flow="imputation.spline",
        metrics={
            "n_rows": int(len(out)),
            "n_columns": len(cols),
            "order": int(params.order),
            **audit,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# KNN imputer
# ---------------------------------------------------------------------------


class KNNParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    n_neighbors: int = Field(default=5, ge=1, le=200)
    weights: Literal["uniform", "distance"] = "uniform"


@register_analysis_flow(
    name="imputation.knn",
    namespace="imputation",
    label="KNN imputer",
    description="sklearn KNNImputer over the selected feature matrix.",
    params_model=KNNParams,
    tags=("imputation", "multivariate"),
    optional_dependencies=("scikit-learn",),
)
def knn_flow(
    df: pd.DataFrame, params: KNNParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.impute import KNNImputer
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = _pick_columns(df, params.columns)
    out = df.copy()
    imp = KNNImputer(n_neighbors=int(params.n_neighbors), weights=params.weights)
    out[cols] = imp.fit_transform(out[cols].to_numpy(dtype=float))
    audit = _audit(df[cols], out[cols])
    rows = _truncate_rows(out)
    return FlowResult(
        flow="imputation.knn",
        metrics={
            "n_rows": int(len(out)),
            "n_columns": len(cols),
            "n_neighbors": int(params.n_neighbors),
            "weights": params.weights,
            **audit,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# MICE (IterativeImputer)
# ---------------------------------------------------------------------------


class MICEParams(FlowParams):
    columns: list[str] = Field(default_factory=list)
    max_iter: int = Field(default=10, ge=1, le=200)
    random_state: int | None = 42


@register_analysis_flow(
    name="imputation.mice",
    namespace="imputation",
    label="MICE (IterativeImputer)",
    description=(
        "Multiple Imputation by Chained Equations via sklearn "
        "IterativeImputer (BayesianRidge regressor by default)."
    ),
    params_model=MICEParams,
    tags=("imputation", "multivariate", "mice"),
    optional_dependencies=("scikit-learn",),
)
def mice_flow(
    df: pd.DataFrame, params: MICEParams, ctx: FlowContext
) -> FlowResult:
    try:
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "scikit-learn is not installed. Install via the `ml` extra."
        ) from exc
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = _pick_columns(df, params.columns)
    out = df.copy()
    imp = IterativeImputer(
        max_iter=int(params.max_iter),
        random_state=params.random_state,
    )
    out[cols] = imp.fit_transform(out[cols].to_numpy(dtype=float))
    audit = _audit(df[cols], out[cols])
    rows = _truncate_rows(out)
    return FlowResult(
        flow="imputation.mice",
        metrics={
            "n_rows": int(len(out)),
            "n_columns": len(cols),
            "max_iter": int(params.max_iter),
            **audit,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# Stub np reference so unused-import linters don't fire when np helpers
# above are conditionally absent.
_ = np


__all__ = [
    "FfillBfillParams",
    "KNNParams",
    "LinearInterpParams",
    "MICEParams",
    "SplineParams",
    "ffill_bfill_flow",
    "knn_flow",
    "linear_interp_flow",
    "mice_flow",
    "spline_interp_flow",
]
