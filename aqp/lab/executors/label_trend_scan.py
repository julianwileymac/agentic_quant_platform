"""``label.trend_scan`` — López de Prado trend-scanning labels.

Wraps :func:`aqp.ml.labeling.trend_scanning.trend_scanning_labels`
on the upstream BAR_SERIES frame.

Params:

- ``price_column`` (str, default ``"close"``).
- ``t_horizons`` (list[int], default ``[5, 10, 21]``) — forward
  windows the trend scanner regresses on.

Emits an ANNOTATION_SET frame with columns ``[t1, horizon, t_stat,
slope, label]`` indexed by the upstream timestamp (rule 39 AST
sandbox does not apply — this is pure pandas / numpy, no user code
execution).
"""
from __future__ import annotations

import logging
from typing import Any

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
    price_column = str(params.get("price_column") or "close")
    horizons_raw = params.get("t_horizons") or [5, 10, 21]
    if not isinstance(horizons_raw, (list, tuple)) or not horizons_raw:
        return NodeResult(
            status="error",
            error="label.trend_scan: params.t_horizons must be a non-empty list of ints",
            log_label="label.trend_scan:bad_horizons",
        )
    try:
        horizons = tuple(int(h) for h in horizons_raw)
    except (TypeError, ValueError) as exc:
        return NodeResult(
            status="error",
            error=f"label.trend_scan: invalid t_horizons {horizons_raw!r}: {exc}",
            log_label="label.trend_scan:bad_horizons",
        )

    df = resolve_upstream_frame(ctx)
    if df is None or price_column not in df.columns:
        return NodeResult(
            status="error",
            error=f"label.trend_scan: upstream frame missing column {price_column!r}",
            log_label="label.trend_scan:no_price",
        )
    if len(df) < max(horizons) + 1:
        return NodeResult(
            status="error",
            error=(
                f"label.trend_scan: series of length {len(df)} too short for "
                f"max horizon {max(horizons)}"
            ),
            log_label="label.trend_scan:short_series",
        )

    try:
        from aqp.ml.labeling.trend_scanning import trend_scanning_labels
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"trend_scanning_labels import failed: {exc}",
            log_label="label.trend_scan:import_fail",
        )

    close = df[price_column].astype(float).reset_index(drop=False)
    if "datetime" in close.columns:
        idx = close["datetime"]
        series = pd.Series(close[price_column].values, index=idx, name=price_column)
    elif "index" in close.columns:
        series = pd.Series(close[price_column].values, index=close["index"], name=price_column)
    else:
        series = pd.Series(close[price_column].values, name=price_column)

    try:
        labels = trend_scanning_labels(series, t_horizons=horizons)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"trend_scanning_labels failed: {exc}",
            log_label="label.trend_scan:execute_fail",
        )

    out = labels.reset_index()
    stash_arrow_output(ctx, node.id, out)
    n_pos = int((out["label"] == 1).sum()) if not out.empty else 0
    n_neg = int((out["label"] == -1).sum()) if not out.empty else 0
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out, kind="trend_scan"),
            "price_column": price_column,
            "t_horizons": list(horizons),
        },
        metrics={
            "rows": int(len(out)),
            "positive_count": n_pos,
            "negative_count": n_neg,
            "abs_t_stat_max": float(out["t_stat"].abs().max()) if not out.empty else 0.0,
        },
        log_label=f"label.trend_scan:{price_column}",
    )


__all__ = ["execute"]
