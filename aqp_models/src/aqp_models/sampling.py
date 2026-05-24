"""Sample-uniqueness weighting + sequential bootstrap (AFML ch. 4).

Financial observations are not IID — overlapping labels share information
so naive bootstrap resamples them more than they deserve. AFML fixes the
bias with:

* :func:`num_concurrent_events` — count how many events are live at each
  bar.
* :func:`average_uniqueness` — per-event uniqueness ∈ (0, 1].
* :func:`sample_weights_by_return` — final weights = uniqueness × |return|.
* :func:`sequential_bootstrap` — draw bootstrap indices that penalise
  overlap via in-sample uniqueness.
"""
from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def num_concurrent_events(close_index: pd.DatetimeIndex, events: pd.DataFrame) -> pd.Series:
    """Return a series indexed by ``close_index`` with the number of events
    that are "live" at each bar.

    ``events`` must have a ``t1`` column (the event end-time). The event's
    start is its index.
    """
    counts = pd.Series(0, index=close_index, dtype=int)
    for start, end in events["t1"].dropna().items():
        counts.loc[start:end] += 1
    return counts


def average_uniqueness(events: pd.DataFrame, close_index: pd.DatetimeIndex) -> pd.Series:
    """Uniqueness = mean(1 / concurrent_events) over the event window."""
    counts = num_concurrent_events(close_index, events)
    weights = pd.Series(index=events.index, dtype=float)
    for start, end in events["t1"].dropna().items():
        live = counts.loc[start:end].replace(0, np.nan)
        weights.loc[start] = (1.0 / live).mean()
    return weights.fillna(0.0)


def sample_weights_by_return(
    events: pd.DataFrame,
    close: pd.Series,
) -> pd.Series:
    """AFML eq. 4.10: weight = uniqueness × |log return|, normalised to 1."""
    if events.empty:
        return pd.Series(dtype=float)
    counts = num_concurrent_events(close.index, events)
    log_ret = np.log(close).diff().fillna(0.0)
    w = pd.Series(index=events.index, dtype=float)
    for start, end in events["t1"].dropna().items():
        live = counts.loc[start:end].replace(0, np.nan)
        w.loc[start] = float((log_ret.loc[start:end] / live).sum())
    w = w.abs()
    total = w.sum()
    return w / total if total > 0 else w


def _indicator_matrix(close_index: pd.DatetimeIndex, events: pd.DataFrame) -> pd.DataFrame:
    """Binary matrix (bars × events) used by the sequential bootstrap."""
    mat = pd.DataFrame(0, index=close_index, columns=events.index, dtype=int)
    for eid, (start, end) in events["t1"].dropna().items():
        mat.loc[start:end, eid] = 1
    return mat


def sequential_bootstrap(
    events: pd.DataFrame,
    close_index: pd.DatetimeIndex,
    sample_length: int | None = None,
    rng: np.random.Generator | None = None,
) -> list[int]:
    """Sequentially sample event indices, downweighting overlapping ones."""
    if events.empty:
        return []
    rng = rng or np.random.default_rng()
    ind = _indicator_matrix(close_index, events)
    phi: list[int] = []
    length = sample_length or len(events)
    while len(phi) < length:
        avg_u = pd.Series(dtype=float)
        for eid in ind.columns:
            ind_ = ind[[*phi, eid]] if phi else ind[[eid]]
            c = ind_.sum(axis=1)
            u = ind[eid] / c.replace(0, np.nan)
            avg_u.loc[eid] = float(u[ind[eid] == 1].mean())
        avg_u = avg_u.fillna(0.0)
        total = avg_u.sum()
        if total <= 0:
            chosen = rng.choice(ind.columns)
        else:
            chosen = rng.choice(ind.columns, p=(avg_u / total).values)
        phi.append(chosen)
    return phi


def time_decay(weights: pd.Series, decay: float = 1.0) -> pd.Series:
    """Apply AFML's time-decay to a weight series.

    ``decay=1.0`` keeps the weights unchanged. Values in ``[0, 1)`` fade
    older observations linearly down to ``decay × w_max``. Negative
    values fade older observations down to zero (abrupt cutoff).
    """
    if weights.empty:
        return weights
    cum = weights.sort_index().cumsum()
    total = cum.iloc[-1]
    if total <= 0:
        return weights
    cum /= total
    if decay >= 0:
        slope = (1 - decay) / cum.max() if cum.max() > 0 else 0.0
        intercept = 1 - slope * cum.max()
    else:
        slope = 1.0 / ((decay + 1) * cum.max()) if cum.max() > 0 else 0.0
        intercept = -slope * decay * cum.max()
    multiplier = (slope * cum + intercept).clip(lower=0.0)
    return weights * multiplier


__all__ = [
    "average_uniqueness",
    "num_concurrent_events",
    "sample_weights_by_return",
    "sequential_bootstrap",
    "time_decay",
]
