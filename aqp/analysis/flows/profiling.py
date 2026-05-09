"""Profiling flows — column-level audit + dtype + topk + null census.

Wraps the existing :func:`aqp.data.profiling.profiler.compute_profile`
behind the :func:`register_analysis_flow` decorator so the lab UI
gets a uniform schema-driven form. The heavy lifting still happens
in the existing module — this file is purely a facade.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------


class DescribeParams(FlowParams):
    columns: list[str] = Field(
        default_factory=list,
        description="Restrict the profile to these columns. Empty = all.",
    )
    topk: int = Field(default=10, ge=1, le=50)
    sample_rows: int = Field(default=200_000, ge=1, le=2_000_000)


class NullAuditParams(FlowParams):
    columns: list[str] = Field(default_factory=list)


class TopKParams(FlowParams):
    column: str
    topk: int = Field(default=10, ge=1, le=200)


class DtypeParams(FlowParams):
    columns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# describe — full Arrow-native profile
# ---------------------------------------------------------------------------


@register_analysis_flow(
    name="profiling.describe",
    namespace="profiling",
    label="Column profile",
    description=(
        "Per-column null fraction, dtype, distinct estimate, min / max, "
        "and top-k value counts. Wraps aqp.data.profiling.compute_profile."
    ),
    params_model=DescribeParams,
    output_kind="table",
    tags=("profiling", "audit"),
)
def describe_flow(
    df: pd.DataFrame, params: DescribeParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.profiling.profiler import compute_profile

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    frame = df[list(params.columns)] if params.columns else df

    try:
        import pyarrow as pa

        arrow_table = pa.Table.from_pandas(frame, preserve_index=False)
    except Exception:  # noqa: BLE001
        return FlowResult(
            flow="profiling.describe",
            metrics={"error": "pyarrow unavailable"},
        )
    profile = compute_profile(
        arrow_table,
        topk=int(params.topk),
        sample_rows=int(params.sample_rows),
    )
    rows = profile.get("columns", []) or []
    rows_arrow = coerce_arrow([_strip_topk(r) for r in rows])
    return FlowResult(
        flow="profiling.describe",
        metrics={
            "rows": int(profile.get("rows", 0)),
            "bytes": int(profile.get("bytes", 0)),
            "n_columns": len(rows),
            "engine": profile.get("engine", "local"),
        },
        rows=rows[:200],
        artifacts={"profile": profile},
        arrow_table=rows_arrow,
    )


def _strip_topk(row: dict[str, Any]) -> dict[str, Any]:
    """Drop topk for the Iceberg sink — keep the per-column scalar fields."""
    out = {k: v for k, v in row.items() if k != "topk"}
    return out


# ---------------------------------------------------------------------------
# null_audit — JSON-friendly null fractions
# ---------------------------------------------------------------------------


@register_analysis_flow(
    name="profiling.null_audit",
    namespace="profiling",
    label="Null audit",
    description="Per-column null counts + null fractions for the selected columns.",
    params_model=NullAuditParams,
    output_kind="table",
    tags=("profiling", "data_quality"),
)
def null_audit_flow(
    df: pd.DataFrame, params: NullAuditParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = list(params.columns) if params.columns else list(df.columns)
    n = len(df)
    rows: list[dict[str, Any]] = []
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        nulls = int(s.isna().sum())
        rows.append(
            {
                "column": col,
                "nulls": nulls,
                "null_fraction": float(nulls) / n if n else 0.0,
                "n_rows": int(n),
                "dtype": str(s.dtype),
            }
        )
    return FlowResult(
        flow="profiling.null_audit",
        metrics={
            "n_rows": int(n),
            "n_columns": len(rows),
            "max_null_fraction": (
                float(max(r["null_fraction"] for r in rows)) if rows else 0.0
            ),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# topk — value counts for a single column
# ---------------------------------------------------------------------------


@register_analysis_flow(
    name="profiling.topk",
    namespace="profiling",
    label="Top-K values",
    description="Top-K most frequent values for a column with counts + share.",
    params_model=TopKParams,
    output_kind="table",
    tags=("profiling", "categorical"),
)
def topk_flow(
    df: pd.DataFrame, params: TopKParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.column not in df.columns:
        return FlowResult(
            flow="profiling.topk",
            metrics={"error": f"column {params.column!r} not found"},
        )
    s = df[params.column].dropna()
    counts = s.value_counts().head(int(params.topk))
    total = int(len(s))
    rows = [
        {
            "value": _stringify(idx),
            "count": int(cnt),
            "share": float(cnt) / total if total else 0.0,
        }
        for idx, cnt in counts.items()
    ]
    return FlowResult(
        flow="profiling.topk",
        metrics={
            "column": params.column,
            "n_unique": int(s.nunique()),
            "n_observed": total,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


def _stringify(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return repr(value)


# ---------------------------------------------------------------------------
# dtypes — schema-only summary
# ---------------------------------------------------------------------------


@register_analysis_flow(
    name="profiling.dtypes",
    namespace="profiling",
    label="Dtypes",
    description="Per-column inferred dtype + memory footprint estimate.",
    params_model=DtypeParams,
    output_kind="table",
    tags=("profiling", "schema"),
)
def dtypes_flow(
    df: pd.DataFrame, params: DtypeParams, ctx: FlowContext
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = list(params.columns) if params.columns else list(df.columns)
    rows: list[dict[str, Any]] = []
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col]
        sample = s.dropna()
        rows.append(
            {
                "column": col,
                "dtype": str(s.dtype),
                "n": int(len(s)),
                "n_non_null": int(len(sample)),
                "memory_bytes": int(s.memory_usage(deep=True)),
                "sample_value": _stringify(sample.iloc[0]) if len(sample) else None,
            }
        )
    return FlowResult(
        flow="profiling.dtypes",
        metrics={"n_columns": len(rows), "n_rows": int(len(df))},
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


__all__ = [
    "DescribeParams",
    "DtypeParams",
    "NullAuditParams",
    "TopKParams",
    "describe_flow",
    "dtypes_flow",
    "null_audit_flow",
    "topk_flow",
]


# Stub np reference to silence unused-import warnings in some lints.
_ = np
