"""``xform.resample`` — time-bar resample over an upstream OHLCV frame.

Params:

- ``rule`` (str, default ``"5min"``) — pandas offset alias.
- ``aggregations`` (dict[str, str] | None) — column → agg map; defaults
  to OHLCV semantics: ``{open:first, high:max, low:min, close:last, volume:sum}``.
- ``timestamp_column`` (str, default ``"timestamp"``).
"""
from __future__ import annotations

import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    rule = str(params.get("rule") or "5min")
    ts_col = str(params.get("timestamp_column") or "timestamp")
    aggs = dict(params.get("aggregations") or {})
    df = resolve_upstream_frame(ctx)
    if df is None or ts_col not in df.columns:
        return NodeResult(
            status="error",
            error=f"xform.resample requires an upstream frame with '{ts_col}' column",
        )
    out = df.copy()
    out[ts_col] = pd.to_datetime(out[ts_col], errors="coerce")
    out = out.set_index(ts_col)
    default_aggs = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    effective_aggs = {**default_aggs, **aggs}
    keep = {c: a for c, a in effective_aggs.items() if c in out.columns}
    if not keep:
        # Fall back to numeric mean if no OHLCV columns are present.
        keep = {c: "mean" for c in out.select_dtypes("number").columns}
    resampled = out.resample(rule).agg(keep).dropna(how="all").reset_index()
    stash_arrow_output(ctx, node.id, resampled)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, resampled),
            "rule": rule,
        },
        metrics={"rule": rule, "rows": int(len(resampled))},
        log_label=f"resample:{rule}",
    )
