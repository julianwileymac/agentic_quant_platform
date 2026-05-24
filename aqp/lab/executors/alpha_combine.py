"""``alpha.combine`` — linear / rank / equal-weight alpha combiner."""
from __future__ import annotations

import numpy as np

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    method = str(params.get("method") or "equal").lower()
    weights = params.get("weights") or {}
    alpha_cols = params.get("alpha_columns") or []
    alias = str(params.get("alias") or "alpha_combo")

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(status="error", error="alpha.combine needs an upstream frame")
    cols = [c for c in alpha_cols if c in df.columns] or [
        c for c in df.columns if c.startswith("alpha")
    ]
    if not cols:
        return NodeResult(status="error", error="alpha.combine: no alpha columns found")

    out = df.copy()
    if method == "linear":
        w = np.array([float(weights.get(c, 1.0)) for c in cols], dtype=float)
        wsum = w.sum() or 1.0
        out[alias] = (out[cols].to_numpy(dtype=float) * w[None, :]).sum(axis=1) / wsum
    elif method == "rank":
        ranks = out[cols].rank(pct=True).mean(axis=1)
        out[alias] = ranks - 0.5
    else:  # equal-weight average
        out[alias] = out[cols].mean(axis=1)
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, out), "method": method, "n_inputs": len(cols)},
        metrics={"method": method, "n_inputs": len(cols)},
        log_label=f"alpha_combine:{method}",
    )
