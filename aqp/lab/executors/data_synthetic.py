"""``data.synthetic`` — render the upstream ``math.*`` path as a BAR_SERIES.

Wraps an upstream stochastic / regime simulator node into a Frame the
downstream Feature / Strategy nodes can read. The upstream node's
output is expected to be a wide DataFrame with one column per
timestep (e.g. ``step_0`` … ``step_N``) and one row per path — the
shape produced by :mod:`aqp.lab.executors.math_gbm` and the future
Heston / OU / regime simulators.

Params:

- ``path_index`` (int, default 0) — which path to render.
- ``output_columns`` (Literal['close','ohlcv'], default 'close') —
  when ``ohlcv`` we synthesise (open, high, low, close, volume) per
  bar from the close series (open = prior close, h/l = close ±
  jitter, volume = constant) so downstream technical-indicator
  executors that expect OHLCV work without extra wiring.
- ``volume`` (float, default 1.0) — constant volume column.
- ``jitter_pct`` (float, default 0.001) — high/low jitter as a
  fraction of close.
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
    path_index = int(params.get("path_index") or 0)
    output_columns = str(params.get("output_columns") or "close").lower()
    volume = float(params.get("volume") or 1.0)
    jitter_pct = float(params.get("jitter_pct") or 0.001)

    upstream = resolve_upstream_frame(ctx)
    if upstream is None:
        return NodeResult(
            status="error",
            error="data.synthetic requires an upstream math.* frame (no upstream wired)",
            log_label="data.synthetic:no_upstream",
        )

    # Two upstream shapes are supported:
    #
    # 1. Wide: ``step_0, step_1, ...`` columns + a ``path_id`` row index
    #    (the shape :mod:`math_gbm` emits).
    # 2. Long: ``[ts, close]`` columns from a regime / HMM simulator.
    if "path_id" in upstream.columns and any(
        col.startswith("step_") for col in upstream.columns
    ):
        step_cols = [c for c in upstream.columns if c.startswith("step_")]
        if path_index >= len(upstream):
            return NodeResult(
                status="error",
                error=f"path_index={path_index} out of range (n_paths={len(upstream)})",
                log_label="data.synthetic:bad_index",
            )
        close = pd.Series(
            upstream.loc[path_index, step_cols].astype(float).to_list(),
            index=pd.RangeIndex(len(step_cols), name="step"),
            name="close",
        )
    elif "close" in upstream.columns:
        close = upstream["close"].astype(float).reset_index(drop=True)
    else:
        return NodeResult(
            status="error",
            error="data.synthetic: upstream frame must carry step_* columns or a close column",
            log_label="data.synthetic:bad_shape",
        )

    if output_columns == "close":
        out = close.to_frame(name="close")
    elif output_columns == "ohlcv":
        out = _render_ohlcv(close, volume=volume, jitter_pct=jitter_pct)
    else:
        return NodeResult(
            status="error",
            error=f"data.synthetic: unknown output_columns {output_columns!r}",
            log_label="data.synthetic:bad_output",
        )

    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out, kind="synthetic"),
            "path_index": path_index,
            "output_columns": output_columns,
        },
        metrics={
            "rows": int(len(out)),
            "cols": int(out.shape[1]),
        },
        log_label=f"data.synthetic:path={path_index}",
    )


def _render_ohlcv(close: pd.Series, *, volume: float, jitter_pct: float) -> pd.DataFrame:
    """Cheap synthetic OHLCV given a close series."""
    close_values = close.to_numpy(dtype=float)
    open_values = np.concatenate(([close_values[0]], close_values[:-1]))
    high = np.maximum(close_values, open_values) * (1.0 + jitter_pct)
    low = np.minimum(close_values, open_values) * (1.0 - jitter_pct)
    return pd.DataFrame(
        {
            "open": open_values,
            "high": high,
            "low": low,
            "close": close_values,
            "volume": np.full_like(close_values, volume),
        }
    )


__all__ = ["execute"]
