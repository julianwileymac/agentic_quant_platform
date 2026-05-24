"""``feature.fracdiff`` — López de Prado's fixed-width fractional differentiation.

Achieves stationarity while preserving memory. The fixed-width window
implementation here mirrors the FFD weights formula in *Advances in
Financial Machine Learning* ch.5; the unbounded ``frac_diff`` variant
is a Phase 5 follow-up.

Params:

- ``d`` (float, default 0.4) — differentiation order in (0, 1).
- ``threshold`` (float, default 1e-4) — weight cutoff.
- ``column`` (str, default ``"close"``).
- ``alias`` (str, default ``"ffd_<col>"``).
"""
from __future__ import annotations

import numpy as np

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def _ffd_weights(d: float, threshold: float) -> np.ndarray:
    w = [1.0]
    k = 1
    while True:
        nw = -w[-1] / k * (d - k + 1)
        if abs(nw) < threshold:
            break
        w.append(nw)
        k += 1
        if k > 5000:  # safety cap
            break
    return np.array(w[::-1])


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    d = float(params.get("d") or 0.4)
    threshold = float(params.get("threshold") or 1e-4)
    column = str(params.get("column") or "close")
    alias = str(params.get("alias") or f"ffd_{column}")

    if not 0.0 < d < 1.0:
        return NodeResult(
            status="error",
            error=f"feature.fracdiff requires 0 < d < 1; got {d}",
        )

    df = resolve_upstream_frame(ctx)
    if df is None or column not in df.columns:
        return NodeResult(
            status="error",
            error=f"feature.fracdiff needs upstream frame with '{column}' column",
        )

    w = _ffd_weights(d, threshold)
    series = df[column].to_numpy(dtype=float)
    width = len(w)
    out_values = np.full(len(series), np.nan)
    for i in range(width - 1, len(series)):
        window = series[i - width + 1 : i + 1]
        out_values[i] = float((w * window).sum())
    out = df.copy()
    out[alias] = out_values
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out),
            "d": d,
            "weight_count": int(width),
        },
        metrics={"d": d, "weight_count": int(width)},
        log_label=f"fracdiff:d={d}",
    )
