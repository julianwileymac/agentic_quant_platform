"""Trend-scanning labels (López de Prado, AFML ch. 5).

For each observation, run a set of OLS regressions on the forward price
window of length in ``t_horizons``; keep the horizon whose absolute
``t``-stat is largest and emit ``sign(slope)`` with that value as
confidence weight.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.core.registry import labeling


def _max_tval_slope(y: np.ndarray) -> tuple[float, float]:
    """Return (t_stat, slope) of the OLS regression of ``y`` on its index."""
    n = len(y)
    if n < 3:
        return 0.0, 0.0
    x = np.arange(n, dtype=float)
    x_bar = x.mean()
    y_bar = y.mean()
    ssx = ((x - x_bar) ** 2).sum()
    if ssx <= 0:
        return 0.0, 0.0
    slope = ((x - x_bar) * (y - y_bar)).sum() / ssx
    intercept = y_bar - slope * x_bar
    resid = y - (intercept + slope * x)
    sse = float((resid**2).sum())
    if n <= 2 or sse <= 0:
        return 0.0, float(slope)
    se = np.sqrt(sse / (n - 2) / ssx)
    if se <= 0:
        return 0.0, float(slope)
    return float(slope / se), float(slope)


@labeling("TrendScanningLabels")
def trend_scanning_labels(
    close: pd.Series,
    t_horizons: tuple[int, ...] = (5, 10, 21),
) -> pd.DataFrame:
    """Return ``{t1, horizon, t_stat, slope, label}`` per observation.

    ``label = sign(slope)`` for the horizon with the largest absolute
    ``t``-stat. Rows near the end of the series where no horizon fits
    fully are dropped.
    """
    out: list[dict[str, object]] = []
    values = close.values
    idx = close.index
    for i, ts in enumerate(idx):
        best = (0.0, 0.0, 0)
        best_end: int | None = None
        for h in t_horizons:
            end = i + int(h)
            if end >= len(values):
                continue
            t_stat, slope = _max_tval_slope(values[i : end + 1])
            if abs(t_stat) > abs(best[0]):
                best = (t_stat, slope, int(h))
                best_end = end
        if best_end is None:
            continue
        out.append(
            {
                "datetime": ts,
                "t1": idx[best_end],
                "horizon": best[2],
                "t_stat": best[0],
                "slope": best[1],
                "label": int(np.sign(best[1])),
            }
        )
    if not out:
        return pd.DataFrame(columns=["t1", "horizon", "t_stat", "slope", "label"])
    frame = pd.DataFrame(out).set_index("datetime")
    return frame


__all__ = ["trend_scanning_labels"]
