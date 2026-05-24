"""Triple-barrier labelling (López de Prado, AFML ch. 3).

Given a price series and a set of trigger timestamps, the method marks
each observation according to which of three barriers fires first:

* **Upper** — profit-taking threshold (``+pt * side``).
* **Lower** — stop-loss threshold (``-sl * side``).
* **Vertical** — holding-period expiry.

Exit label is ``+1`` / ``-1`` / ``0`` for upper / lower / vertical.

Register via :func:`aqp.core.registry.labeling` so config-driven
pipelines can resolve it by name.
"""
from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd

from aqp.core.registry import labeling

logger = logging.getLogger(__name__)


def _daily_vol(close: pd.Series, span: int = 100) -> pd.Series:
    """Daily EWMA volatility of log returns (AFML snippet 3.1)."""
    log_ret = np.log(close).diff().fillna(0.0)
    return log_ret.ewm(span=span).std()


def add_vertical_barrier(
    events: pd.DatetimeIndex,
    close: pd.Series,
    num_days: int = 5,
) -> pd.Series:
    """Return the datetime of the vertical barrier for each event."""
    t1 = close.index.searchsorted(events + pd.Timedelta(days=int(num_days)))
    t1 = t1[t1 < close.shape[0]]
    out = pd.Series(close.index[t1], index=events[: t1.shape[0]])
    return out


def apply_triple_barrier(
    close: pd.Series,
    events: pd.DataFrame,
    pt_sl: tuple[float, float],
) -> pd.DataFrame:
    """Identify which barrier fires first for each event.

    ``events`` must have:

    * ``t1`` — vertical barrier timestamp.
    * ``trgt`` — target threshold expressed as a fraction of price.
    * ``side`` — +1 long / -1 short.

    Returns a frame with ``t1`` (fire-time), ``sl`` (stop-loss time), and
    ``pt`` (profit-take time). The earliest of the three is the effective
    exit.
    """
    out = events[["t1"]].copy()
    if pt_sl[0] > 0:
        pt = pt_sl[0] * events["trgt"]
    else:
        pt = pd.Series(np.nan, index=events.index)
    if pt_sl[1] > 0:
        sl = -pt_sl[1] * events["trgt"]
    else:
        sl = pd.Series(np.nan, index=events.index)

    for loc, vertical in events["t1"].fillna(close.index[-1]).items():
        df0 = close.loc[loc:vertical]
        if df0.empty:
            continue
        side = events.at[loc, "side"]
        ret = (df0 / close.at[loc] - 1.0) * side
        if not np.isnan(sl.at[loc]):
            sl_t = ret[ret < sl.at[loc]].index.min()
            out.at[loc, "sl"] = sl_t
        if not np.isnan(pt.at[loc]):
            pt_t = ret[ret > pt.at[loc]].index.min()
            out.at[loc, "pt"] = pt_t
    return out


def get_events(
    close: pd.Series,
    triggers: pd.DatetimeIndex,
    pt_sl: tuple[float, float],
    target: pd.Series | None = None,
    min_ret: float = 0.0,
    num_days: int = 5,
    side: pd.Series | None = None,
) -> pd.DataFrame:
    """Build the ``events`` frame consumed by :func:`apply_triple_barrier`."""
    if target is None:
        target = _daily_vol(close)
    target = target.reindex(triggers).ffill()
    target = target[target > min_ret] if min_ret > 0 else target

    vertical = add_vertical_barrier(triggers, close, num_days=num_days)

    frame = pd.DataFrame(
        {
            "t1": vertical.reindex(target.index),
            "trgt": target,
            "side": 1.0 if side is None else side.reindex(target.index).fillna(1.0),
        }
    )
    out = apply_triple_barrier(close, frame, pt_sl=pt_sl)
    frame["t1"] = out.min(axis=1, numeric_only=False)
    return frame


@labeling("TripleBarrierLabels")
def triple_barrier_labels(
    close: pd.Series,
    triggers: Iterable[pd.Timestamp] | pd.DatetimeIndex,
    pt_sl: tuple[float, float] = (1.0, 1.0),
    target: pd.Series | None = None,
    min_ret: float = 0.0,
    num_days: int = 5,
    side: pd.Series | None = None,
) -> pd.DataFrame:
    """Return ``{t1, ret, bin}`` per trigger timestamp.

    ``bin`` ∈ ``{-1, 0, +1}`` — -1/+1 if the stop-loss / profit-take
    barrier fired, 0 if the vertical barrier fired first.
    """
    triggers = pd.DatetimeIndex(list(triggers))
    events = get_events(
        close=close,
        triggers=triggers,
        pt_sl=pt_sl,
        target=target,
        min_ret=min_ret,
        num_days=num_days,
        side=side,
    )
    events = events.dropna(subset=["t1"])  # events that never resolved
    ret = close.loc[events["t1"].values].values / close.loc[events.index].values - 1.0
    ret *= events["side"].values
    frame = pd.DataFrame(
        {
            "t1": events["t1"].values,
            "ret": ret,
            "trgt": events["trgt"].values,
            "side": events["side"].values,
        },
        index=events.index,
    )
    frame["bin"] = np.sign(frame["ret"]).astype(int)
    frame.loc[frame["ret"].abs() < frame["trgt"] * 0.5, "bin"] = 0
    return frame


__all__ = [
    "add_vertical_barrier",
    "apply_triple_barrier",
    "get_events",
    "triple_barrier_labels",
]
