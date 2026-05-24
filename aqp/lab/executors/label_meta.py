"""``label.meta`` — meta-labeling on top of a primary signal.

Wraps :func:`aqp.ml.labeling.meta_labeling.meta_labels`. The
upstream must provide:

- ``primary_side_column`` (default ``"signal"``) — the primary
  model's ``+1`` / ``-1`` directional predictions.
- ``forward_returns_column`` (default ``"forward_return"``) — the
  realised forward return at the same timestamp.

Emits an ANNOTATION_SET frame with columns
``[meta_label, primary_side, forward_return, abstain]``.

Params:

- ``primary_side_column`` (str, default ``"signal"``).
- ``forward_returns_column`` (str, default ``"forward_return"``).
- ``abstain_threshold`` (float, default 0.0) — drop rows where the
  absolute forward return is below this threshold.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    side_col = str(params.get("primary_side_column") or "signal")
    ret_col = str(params.get("forward_returns_column") or "forward_return")
    abstain_threshold = float(params.get("abstain_threshold") or 0.0)

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="label.meta requires an upstream frame with primary side + forward return columns",
            log_label="label.meta:no_upstream",
        )
    if side_col not in df.columns or ret_col not in df.columns:
        return NodeResult(
            status="error",
            error=(
                f"label.meta: upstream frame missing column(s); "
                f"need {side_col!r} and {ret_col!r}"
            ),
            log_label="label.meta:missing_columns",
        )

    try:
        from aqp.ml.labeling.meta_labeling import meta_labels
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"meta_labels import failed: {exc}",
            log_label="label.meta:import_fail",
        )

    side_series = df[side_col].astype(float)
    ret_series = df[ret_col].astype(float)
    try:
        labels = meta_labels(
            primary_side=side_series,
            forward_returns=ret_series,
            abstain_threshold=abstain_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"meta_labels execution failed: {exc}",
            log_label="label.meta:execute_fail",
        )

    out = pd.DataFrame(
        {
            "meta_label": labels.astype(int),
            "primary_side": side_series.loc[labels.index].values,
            "forward_return": ret_series.loc[labels.index].values,
        }
    )
    out["abstain"] = (
        ret_series.loc[labels.index].abs() < abstain_threshold
    ).astype(int).values
    if isinstance(labels.index, pd.DatetimeIndex):
        out.insert(0, "datetime", labels.index)
    elif "datetime" in df.columns:
        out.insert(0, "datetime", df.loc[labels.index, "datetime"].values)

    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out, kind="meta_labels"),
            "primary_side_column": side_col,
            "forward_returns_column": ret_col,
            "abstain_threshold": abstain_threshold,
        },
        metrics={
            "rows": int(len(out)),
            "hit_rate": float(np.nanmean(out["meta_label"])) if len(out) else 0.0,
            "n_dropped": int(len(df) - len(out)),
        },
        log_label="label.meta",
    )


__all__ = ["execute"]
