"""``xform.neutralize`` — wraps the BRAIN-semantic neutralization helpers.

Routes through :mod:`aqp.data.expressions_dsl` / :mod:`aqp.data.expressions`
operators (``vector_neut`` / ``group_neutralize`` / ``regression_neut``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def _group_demean(alpha: pd.Series, groups: pd.Series) -> pd.Series:
    return alpha - alpha.groupby(groups).transform("mean")


def _vector_neut(alpha: pd.Series, basis: pd.Series) -> pd.Series:
    a = alpha.to_numpy(dtype=float)
    b = basis.to_numpy(dtype=float)
    denom = float(np.dot(b, b)) or 1.0
    proj = float(np.dot(a, b)) / denom
    return pd.Series(a - proj * b, index=alpha.index)


def _regression_neut(alpha: pd.Series, basis_cols: pd.DataFrame) -> pd.Series:
    X = basis_cols.to_numpy(dtype=float)
    y = alpha.to_numpy(dtype=float)
    # Ordinary least squares + residual.
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:  # noqa: BLE001
        return alpha.copy()
    return pd.Series(y - X @ beta, index=alpha.index)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    method = str(params.get("method") or "group").lower()
    alpha_col = str(params.get("alpha_column") or "alpha")
    df = resolve_upstream_frame(ctx)
    if df is None or alpha_col not in df.columns:
        return NodeResult(
            status="error",
            error=f"xform.neutralize requires upstream frame with '{alpha_col}' column",
        )
    out = df.copy()
    alpha = out[alpha_col]
    if method == "group":
        group_col = str(params.get("group_column") or "sector")
        if group_col not in out.columns:
            return NodeResult(
                status="error",
                error=f"xform.neutralize(method='group') needs '{group_col}' column",
            )
        out[alpha_col] = _group_demean(alpha, out[group_col])
    elif method == "vector":
        basis_col = str(params.get("basis_column") or "market_beta")
        if basis_col not in out.columns:
            return NodeResult(
                status="error",
                error=f"xform.neutralize(method='vector') needs '{basis_col}' column",
            )
        out[alpha_col] = _vector_neut(alpha, out[basis_col])
    elif method == "regression":
        basis_cols = list(params.get("basis_columns") or [])
        missing = [c for c in basis_cols if c not in out.columns]
        if not basis_cols or missing:
            return NodeResult(
                status="error",
                error=f"xform.neutralize(method='regression') needs basis_columns; missing {missing}",
            )
        out[alpha_col] = _regression_neut(alpha, out[basis_cols])
    else:
        return NodeResult(
            status="error",
            error=f"xform.neutralize: unknown method {method!r}",
        )
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, out), "method": method},
        metrics={"method": method},
        log_label=f"neutralize:{method}",
    )
