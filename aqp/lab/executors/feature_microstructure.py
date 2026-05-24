"""``feature.microstructure`` — wraps :mod:`aqp.data.microstructure` helpers.

Phase 2 ships the canonical microstructure feature set: order-book
imbalance, microprice, weighted spread, depth slope, VPIN, trade-flow
imbalance, midprice / spread / relative spread.

Params:

- ``measure`` (str, required) — one of ``imbalance`` / ``microprice`` /
  ``weighted_spread`` / ``depth_slope`` / ``trade_flow_imbalance`` /
  ``vpin`` / ``midprice`` / ``spread`` / ``relative_spread``.
- ``alias`` (str | None) — output column name.
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
    measure = str(params.get("measure") or "imbalance").lower()
    alias = str(params.get("alias") or measure)

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="feature.microstructure needs an upstream LOB or trade frame",
        )
    out = df.copy()

    try:
        from aqp.data import microstructure as ms
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"microstructure import failed: {exc}")

    try:
        if measure == "imbalance":
            out[alias] = ms.order_book_imbalance(out["bid_qty"], out["ask_qty"])
        elif measure == "microprice":
            out[alias] = ms.microprice(
                out["bid_price"], out["ask_price"], out["bid_qty"], out["ask_qty"]
            )
        elif measure == "weighted_spread":
            out[alias] = ms.weighted_spread(
                out["bid_price"], out["ask_price"], out["bid_qty"], out["ask_qty"]
            )
        elif measure == "depth_slope":
            out[alias] = ms.depth_slope(
                out["bid_price"], out["ask_price"], out["bid_qty"], out["ask_qty"]
            )
        elif measure == "trade_flow_imbalance":
            out[alias] = ms.trade_flow_imbalance(out["trade_qty"], out["trade_side"])
        elif measure == "vpin":
            bucket_size = float(params.get("bucket_size") or 50.0)
            window = int(params.get("window") or 50)
            out[alias] = ms.vpin(
                out["trade_qty"], out["trade_side"], bucket_size=bucket_size, window=window
            )
        elif measure == "midprice":
            out[alias] = ms.midprice(out["bid_price"], out["ask_price"])
        elif measure == "spread":
            out[alias] = ms.spread(out["bid_price"], out["ask_price"])
        elif measure == "relative_spread":
            out[alias] = ms.relative_spread(out["bid_price"], out["ask_price"])
        else:
            return NodeResult(
                status="error",
                error=f"feature.microstructure: unknown measure {measure!r}",
            )
    except KeyError as exc:
        return NodeResult(
            status="error",
            error=f"feature.microstructure: upstream missing column {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"feature.microstructure failed: {exc}")
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, out), "measure": measure},
        metrics={"measure": measure},
        log_label=f"microstructure:{measure}",
    )
