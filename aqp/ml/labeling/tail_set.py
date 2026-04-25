"""Tail-set labels — keep only extreme winners / losers.

Classification models often under-perform when most observations hover
around zero return. :func:`tail_set_labels` filters to the top / bottom
``q`` percentile per-day and labels them ``+1`` / ``-1``; mid-quantile
rows are dropped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.core.registry import labeling


@labeling("TailSetLabels")
def tail_set_labels(
    forward_returns: pd.Series | pd.DataFrame,
    q: float = 0.1,
    by_date: bool = True,
) -> pd.DataFrame:
    """Return a frame with ``label`` ∈ {-1, 0, +1}.

    When ``by_date`` is true (default), the percentile cut is recomputed
    at each date so the tail-set is balanced cross-sectionally rather
    than across the entire sample.
    """
    if isinstance(forward_returns, pd.DataFrame):
        series = forward_returns.stack()
    else:
        series = forward_returns.copy()

    if by_date and isinstance(series.index, pd.MultiIndex):
        top = series.groupby(level=0).transform(lambda s: s.quantile(1 - q))
        bot = series.groupby(level=0).transform(lambda s: s.quantile(q))
    else:
        top = pd.Series(series.quantile(1 - q), index=series.index)
        bot = pd.Series(series.quantile(q), index=series.index)

    label = pd.Series(0, index=series.index, dtype=int)
    label.loc[series >= top] = 1
    label.loc[series <= bot] = -1
    out = pd.DataFrame({"ret": series, "label": label})
    out = out[out["label"] != 0]
    return out


__all__ = ["tail_set_labels"]
