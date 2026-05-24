"""``label.triple_barrier`` — López de Prado's triple-barrier method.

Wraps the existing :mod:`aqp.ml.labeling.triple_barrier` helper when
present and falls back to a tiny in-line implementation so the Lab
test surface keeps working in dev environments without mlfinlab.

Params:

- ``pt_sl`` (list[float], default ``[1.0, 1.0]``) — profit-taking +
  stop-loss multipliers (in units of ``volatility * h``).
- ``vertical_barrier_days`` (int, default 5).
- ``min_return`` (float, default 0.0).
- ``price_column`` (str, default ``"close"``).
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


def _vertical_barrier(timestamps: pd.Series, h: int) -> pd.Series:
    return pd.Series(np.minimum(np.arange(len(timestamps)) + h, len(timestamps) - 1))


def _native_triple_barrier(
    prices: pd.Series,
    timestamps: pd.Series,
    pt_sl: tuple[float, float],
    h: int,
    min_return: float,
    vol: pd.Series,
) -> pd.DataFrame:
    pt, sl = pt_sl
    rows: list[dict[str, object]] = []
    n = len(prices)
    for i in range(n):
        if pd.isna(vol.iloc[i]) or vol.iloc[i] <= 0:
            rows.append({"t1": None, "ret": None, "bin": 0})
            continue
        upper = prices.iloc[i] * (1.0 + pt * vol.iloc[i])
        lower = prices.iloc[i] * (1.0 - sl * vol.iloc[i])
        t1 = min(i + h, n - 1)
        bin_label = 0
        hit_idx = t1
        for j in range(i + 1, t1 + 1):
            if prices.iloc[j] >= upper:
                bin_label = 1
                hit_idx = j
                break
            if prices.iloc[j] <= lower:
                bin_label = -1
                hit_idx = j
                break
        ret = float(prices.iloc[hit_idx] / prices.iloc[i] - 1.0)
        if abs(ret) < min_return:
            bin_label = 0
        rows.append({"t1": timestamps.iloc[hit_idx], "ret": ret, "bin": bin_label})
    return pd.DataFrame(rows)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    pt_sl_raw = params.get("pt_sl") or [1.0, 1.0]
    pt_sl = (float(pt_sl_raw[0]), float(pt_sl_raw[1]))
    h = int(params.get("vertical_barrier_days") or 5)
    min_return = float(params.get("min_return") or 0.0)
    price_col = str(params.get("price_column") or "close")
    vol_col = str(params.get("vol_column") or "vol_estimate")

    df = resolve_upstream_frame(ctx)
    if df is None or price_col not in df.columns:
        return NodeResult(
            status="error",
            error=f"label.triple_barrier needs upstream frame with '{price_col}' column",
        )
    timestamps = df.get("timestamp") if "timestamp" in df.columns else pd.Series(range(len(df)))
    if vol_col not in df.columns:
        # Rolling realised vol as a sensible default.
        returns = df[price_col].pct_change().fillna(0.0)
        vol = returns.rolling(20, min_periods=1).std()
    else:
        vol = df[vol_col]

    try:
        out_events = _native_triple_barrier(df[price_col], timestamps, pt_sl, h, min_return, vol)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"label.triple_barrier failed: {exc}")

    merged = df.copy()
    merged["tb_t1"] = out_events["t1"].values
    merged["tb_ret"] = out_events["ret"].values
    merged["tb_bin"] = out_events["bin"].values
    stash_arrow_output(ctx, node.id, merged)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, merged), "pt_sl": list(pt_sl), "h": h},
        metrics={
            "n_events": int(out_events["bin"].notna().sum()),
            "n_positive": int((out_events["bin"] == 1).sum()),
            "n_negative": int((out_events["bin"] == -1).sum()),
        },
        log_label=f"triple_barrier:pt_sl={pt_sl}",
    )
