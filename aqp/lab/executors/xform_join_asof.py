"""``xform.join_asof`` — pandas ``merge_asof`` for trades/book correlation."""
from __future__ import annotations

import pandas as pd

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    on = str(params.get("on") or "timestamp")
    direction = str(params.get("direction") or "backward")
    tolerance = params.get("tolerance")  # pandas Timedelta string

    left_loc = ctx.upstream.get("left")
    right_loc = ctx.upstream.get("right")
    if not isinstance(left_loc, dict) or not isinstance(right_loc, dict):
        return NodeResult(status="error", error="xform.join_asof requires 'left' and 'right' upstreams")

    arrow = ctx.extras.get("_arrow_outputs", {}) if ctx.extras else {}
    left_df = arrow.get(left_loc.get("node_id"))
    right_df = arrow.get(right_loc.get("node_id"))
    if left_df is None or right_df is None:
        return NodeResult(
            status="error",
            error="xform.join_asof: cross-process locator materialisation lands in Phase 2",
        )
    left = left_df.to_pandas() if hasattr(left_df, "to_pandas") else left_df
    right = right_df.to_pandas() if hasattr(right_df, "to_pandas") else right_df
    for d in (left, right):
        if on in d.columns:
            d[on] = pd.to_datetime(d[on], errors="coerce")
    left = left.sort_values(on)
    right = right.sort_values(on)
    merge_kwargs: dict = {"on": on, "direction": direction}
    if tolerance:
        merge_kwargs["tolerance"] = pd.Timedelta(tolerance)
    out = pd.merge_asof(left, right, **merge_kwargs)
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator=base_locator(node.id, out),
        metrics={"rows": int(len(out))},
        log_label=f"join_asof:{direction}",
    )
