"""Meta-labelling — train a second model to filter a primary model's bets.

``meta_labels`` takes a primary model's side predictions (``+1``/``-1``)
plus forward returns and emits binary labels indicating whether the
primary model was right (``1``) or wrong (``0``). Feed those into a
meta-classifier (logistic, GBM, ...) to learn when to trust the primary.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.core.registry import labeling


@labeling("MetaLabels")
def meta_labels(
    primary_side: pd.Series,
    forward_returns: pd.Series,
    abstain_threshold: float = 0.0,
) -> pd.Series:
    """Return ``1`` when the primary signal's direction matches the
    forward return, ``0`` otherwise. Rows where the absolute forward
    return is below ``abstain_threshold`` are dropped (not labelled).
    """
    aligned = pd.concat(
        [primary_side.rename("side"), forward_returns.rename("ret")],
        axis=1,
    ).dropna()
    if abstain_threshold > 0:
        aligned = aligned[aligned["ret"].abs() >= abstain_threshold]
    hit = (np.sign(aligned["ret"]) == np.sign(aligned["side"])).astype(int)
    hit.name = "meta_label"
    return hit


__all__ = ["meta_labels"]
