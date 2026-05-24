"""``xform.winsorize`` — quantile clipping per column."""
from __future__ import annotations

from aqp.lab.executors._helpers import (
    base_locator,
    numeric_columns,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    lower_q = float(params.get("lower_q") or 0.01)
    upper_q = float(params.get("upper_q") or 0.99)
    columns = params.get("columns")
    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(status="error", error="xform.winsorize needs an upstream frame")
    out = df.copy()
    cols = numeric_columns(out, columns)
    if not cols:
        return NodeResult(status="error", error="xform.winsorize found no numeric columns to clip")
    for c in cols:
        lo = out[c].quantile(lower_q)
        hi = out[c].quantile(upper_q)
        out[c] = out[c].clip(lower=lo, upper=hi)
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out),
            "lower_q": lower_q,
            "upper_q": upper_q,
        },
        metrics={"lower_q": lower_q, "upper_q": upper_q, "n_cols_clipped": len(cols)},
        log_label=f"winsorize:[{lower_q},{upper_q}]",
    )
