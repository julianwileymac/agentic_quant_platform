"""Walk-forward splitters — anchored (expanding) + rolling (fixed-window).

Both yield ``(train_idx, test_idx)`` tuples compatible with the
sklearn cross-validator contract so they slot into the same
:class:`ValidationExperiment` pipeline as
:class:`CombinatorialPurgedKFold`.

- :func:`walk_forward_anchored`: training window grows; test window
  marches forward.
- :func:`walk_forward_rolling`: training window slides forward
  in lockstep with the test window (constant training horizon).

Both helpers accept an optional ``purge`` to drop the last few rows
of the train window (mimicking the CPCV purge but in the temporal
direction).
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import NamedTuple

import numpy as np


class WalkForwardSplit(NamedTuple):
    """One walk-forward fold."""

    train_idx: np.ndarray
    test_idx: np.ndarray
    fold: int


def walk_forward_anchored(
    n_samples: int,
    *,
    train_size: int,
    test_size: int,
    step: int | None = None,
    purge: int = 0,
) -> Iterator[WalkForwardSplit]:
    """Yield anchored (expanding-window) walk-forward splits.

    - Fold 0: train ``[0 : train_size]``, test ``[train_size : train_size + test_size]``.
    - Fold 1: train ``[0 : train_size + step]``, test ``[... : ...]``.
    - …

    ``step`` defaults to ``test_size`` (no overlap between successive
    test windows). ``purge`` drops the last ``purge`` rows of the
    train window each fold.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0; got {n_samples!r}")
    if train_size < 1 or test_size < 1:
        raise ValueError("train_size and test_size must each be ≥ 1")
    if step is None:
        step = test_size
    if step < 1:
        raise ValueError(f"step must be ≥ 1; got {step!r}")
    if purge < 0:
        raise ValueError(f"purge must be ≥ 0; got {purge!r}")

    fold = 0
    test_start = train_size
    while test_start + test_size <= n_samples:
        train_end = max(0, test_start - purge)
        train_idx = np.arange(0, train_end, dtype=np.int64)
        test_idx = np.arange(test_start, test_start + test_size, dtype=np.int64)
        if len(train_idx) > 0:
            yield WalkForwardSplit(train_idx=train_idx, test_idx=test_idx, fold=fold)
        fold += 1
        test_start += step


def walk_forward_rolling(
    n_samples: int,
    *,
    train_size: int,
    test_size: int,
    step: int | None = None,
    purge: int = 0,
) -> Iterator[WalkForwardSplit]:
    """Yield rolling (fixed-window) walk-forward splits.

    Same shape as :func:`walk_forward_anchored` but the train window
    slides instead of expanding so its size stays constant at
    ``train_size`` rows.
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0; got {n_samples!r}")
    if train_size < 1 or test_size < 1:
        raise ValueError("train_size and test_size must each be ≥ 1")
    if step is None:
        step = test_size
    if step < 1:
        raise ValueError(f"step must be ≥ 1; got {step!r}")
    if purge < 0:
        raise ValueError(f"purge must be ≥ 0; got {purge!r}")

    fold = 0
    test_start = train_size
    while test_start + test_size <= n_samples:
        train_start = test_start - train_size
        train_end = max(train_start, test_start - purge)
        train_idx = np.arange(train_start, train_end, dtype=np.int64)
        test_idx = np.arange(test_start, test_start + test_size, dtype=np.int64)
        if len(train_idx) > 0:
            yield WalkForwardSplit(train_idx=train_idx, test_idx=test_idx, fold=fold)
        fold += 1
        test_start += step


__all__ = [
    "WalkForwardSplit",
    "walk_forward_anchored",
    "walk_forward_rolling",
]
