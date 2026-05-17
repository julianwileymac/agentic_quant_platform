"""Label generators for supervised ML on bars.

Provides a small library of label functions used by SPM / akquant ML
models and by the new dataset preset definitions in
:mod:`aqp.data.dataset_presets`.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def next_bar_binary(close: pd.Series, threshold: float = 0.0) -> pd.Series:
    """Binary label: ``1`` if next bar return > threshold, else ``0``.

    Last value is NaN (no next bar). Output index aligns with ``close``.
    """
    next_ret = close.shift(-1) / close - 1.0
    return (next_ret > threshold).astype("Int8").where(~next_ret.isna())


def n_step_return(close: pd.Series, n: int = 5) -> pd.Series:
    """Forward log-return over ``n`` bars."""
    return np.log(close.shift(-n) / close)


def n_step_classification(
    close: pd.Series,
    n: int = 5,
    bins: tuple[float, ...] = (-0.02, 0.0, 0.02),
) -> pd.Series:
    """Multi-class label from forward ``n``-step return bucketed by ``bins``.

    Default bins produce classes: 0=large-down, 1=mild-down, 2=mild-up, 3=large-up.
    """
    fwd = n_step_return(close, n)
    return pd.Series(np.digitize(fwd, bins), index=close.index, name="forward_class")


def triple_barrier(
    close: pd.Series,
    upper_pct: float = 0.02,
    lower_pct: float = 0.02,
    horizon: int = 20,
) -> pd.Series:
    """Triple-barrier labels per Lopez de Prado (Adv. in Financial ML).

    For each bar, look forward ``horizon`` bars; label is:
    ``+1`` if upper barrier hit first, ``-1`` if lower, ``0`` if horizon reached first.
    """
    upper = close * (1 + upper_pct)
    lower = close * (1 - lower_pct)
    labels = np.zeros(len(close), dtype=np.int8)
    arr = close.to_numpy()
    upper_arr, lower_arr = upper.to_numpy(), lower.to_numpy()
    for i in range(len(arr)):
        end = min(i + horizon + 1, len(arr))
        window = arr[i + 1 : end]
        if len(window) == 0:
            continue
        hit_upper = np.where(window >= upper_arr[i])[0]
        hit_lower = np.where(window <= lower_arr[i])[0]
        first_upper = hit_upper[0] if len(hit_upper) else np.inf
        first_lower = hit_lower[0] if len(hit_lower) else np.inf
        if first_upper < first_lower:
            labels[i] = 1
        elif first_lower < first_upper:
            labels[i] = -1
        else:
            labels[i] = 0
    out = pd.Series(labels, index=close.index, name="triple_barrier")
    out.iloc[-horizon:] = pd.NA
    return out


def zigzag_anchored(close: pd.Series, threshold_pct: float = 0.05) -> pd.Series:
    """ZigZag-anchored direction label.

    Walks the series; flips direction when reversal exceeds ``threshold_pct``.
    Returns ``+1`` for upswing, ``-1`` for downswing.
    """
    arr = close.to_numpy()
    if len(arr) == 0:
        return pd.Series([], index=close.index, dtype=np.int8)
    direction = np.zeros(len(arr), dtype=np.int8)
    pivot = arr[0]
    cur_dir = 0
    for i in range(1, len(arr)):
        change = (arr[i] - pivot) / pivot if pivot else 0.0
        if cur_dir == 0:
            if change >= threshold_pct:
                cur_dir = 1
                pivot = arr[i]
            elif change <= -threshold_pct:
                cur_dir = -1
                pivot = arr[i]
        elif cur_dir == 1:
            if arr[i] > pivot:
                pivot = arr[i]
            elif (arr[i] - pivot) / pivot <= -threshold_pct:
                cur_dir = -1
                pivot = arr[i]
        else:
            if arr[i] < pivot:
                pivot = arr[i]
            elif (arr[i] - pivot) / pivot >= threshold_pct:
                cur_dir = 1
                pivot = arr[i]
        direction[i] = cur_dir
    return pd.Series(direction, index=close.index, name="zigzag")


def fractional_diff(series: pd.Series, d: float = 0.4, threshold: float = 1e-4) -> pd.Series:
    """Fractionally-differenced series (Lopez de Prado).

    Truncated weights for ``|w_i| < threshold``; no NaN backfill — pad with
    leading NaNs equal to the length of the truncated weight vector.
    """
    weights = [1.0]
    k = 1
    while True:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
    weights = np.array(weights[::-1])
    out = np.full(len(series), np.nan)
    arr = series.to_numpy()
    L = len(weights)
    for i in range(L - 1, len(arr)):
        out[i] = float(np.dot(weights, arr[i - L + 1 : i + 1]))
    return pd.Series(out, index=series.index, name=f"frac_diff_{d}")


__all__ = [
    "fractional_diff",
    "n_step_classification",
    "n_step_return",
    "next_bar_binary",
    "triple_barrier",
    "zigzag_anchored",
]
