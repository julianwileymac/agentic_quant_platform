"""Financial-ML labelling primitives (López de Prado, AFML).

Four labelling routines every supervised trading model can consume:

- :func:`triple_barrier_labels` — the go-to labelling for the book's
  meta-labelling pipeline. Marks each observation with ``{1, 0, -1}``
  depending on whether profit-take, stop-loss, or vertical barrier
  fires first.
- :func:`meta_labels` — binary labels (``1`` = primary model's signal
  was right, ``0`` = wrong) used to train a meta-model that filters out
  low-probability bets.
- :func:`tail_set_labels` — extreme-tail labelling that keeps only the
  top / bottom ``q`` quantile of forward returns.
- :func:`trend_scanning_labels` — detects trend direction + strength
  over horizons of length in ``t_horizons`` (sign + absolute t-stat).

Every routine returns a pandas ``DataFrame`` indexed the same as the
input so it plugs straight into :class:`aqp.ml.dataset.DatasetH`.
"""
from __future__ import annotations

from aqp.ml.labeling.meta_labeling import meta_labels
from aqp.ml.labeling.tail_set import tail_set_labels
from aqp.ml.labeling.trend_scanning import trend_scanning_labels
from aqp.ml.labeling.triple_barrier import (
    add_vertical_barrier,
    apply_triple_barrier,
    get_events,
    triple_barrier_labels,
)

__all__ = [
    "add_vertical_barrier",
    "apply_triple_barrier",
    "get_events",
    "meta_labels",
    "tail_set_labels",
    "trend_scanning_labels",
    "triple_barrier_labels",
]
