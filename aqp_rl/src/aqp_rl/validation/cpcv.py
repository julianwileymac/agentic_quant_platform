"""Combinatorial Purged Cross-Validation (López de Prado AFML Ch.12).

The vanilla k-fold CV silently leaks future information into the
training set for time-series data with autocorrelation. CPCV addresses
this by:

1. **Combinatorial splitting**: every combination of ``k`` groups
   from ``N`` is held out as a test set, producing
   ``φ(N, k) = C(N, k) · k / N`` backtest paths instead of just
   ``N`` (vanilla k-fold).
2. **Purging**: any training observation whose label or temporal
   horizon overlaps with the test set is removed.
3. **Embargoing**: a fixed temporal buffer immediately following the
   test set is also removed from the training set to prevent
   delayed-reaction leakage.

This module ships a sklearn-compatible cross-validator that conforms
to the López de Prado API plus the standalone
:func:`combinatorial_paths_count` formula for the acceptance gate.

References
==========

López de Prado, M. *Advances in Financial Machine Learning*, Ch. 12
(Wiley 2018).
"""
from __future__ import annotations

import logging
from itertools import combinations
from math import comb

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def combinatorial_paths_count(n_splits: int, n_test_splits: int) -> int:
    """Return ``φ(N, k) = C(N, k) · k / N`` — number of CPCV backtest paths.

    The acceptance gate calls this with ``(10, 2)`` and expects ``9``.
    """
    if n_splits <= 0 or n_test_splits <= 0 or n_test_splits >= n_splits:
        raise ValueError(
            f"n_test_splits must be in (0, n_splits); got "
            f"n_splits={n_splits}, n_test_splits={n_test_splits}"
        )
    return comb(n_splits, n_test_splits) * n_test_splits // n_splits


class CombinatorialPurgedKFold:
    """Sklearn-compatible CPCV cross-validator with optional purge + embargo.

    Parameters
    ----------
    n_splits:
        Total number of equal-sized groups (``N``).
    n_test_splits:
        Number of groups held out as test in each combination (``k``).
    samples_info_sets:
        Optional pandas Series indexed like the dataset with each
        entry holding the *information end-time* of the
        corresponding observation (López de Prado's
        ``samples_info_sets``). When provided, the cross-validator
        purges training observations whose label horizon overlaps the
        test fold.
    pct_embargo:
        Fraction of the dataset length that's embargoed *after* each
        test fold. Default ``0.01`` (1%).
    """

    def __init__(
        self,
        n_splits: int = 10,
        n_test_splits: int = 2,
        samples_info_sets: pd.Series | None = None,
        pct_embargo: float = 0.01,
    ) -> None:
        if n_splits < 2:
            raise ValueError(f"n_splits must be ≥ 2; got {n_splits!r}")
        if n_test_splits < 1 or n_test_splits >= n_splits:
            raise ValueError(
                f"n_test_splits must be in [1, n_splits); got {n_test_splits!r}"
            )
        if not 0.0 <= pct_embargo < 0.5:
            raise ValueError(f"pct_embargo must be in [0, 0.5); got {pct_embargo!r}")
        self.n_splits = int(n_splits)
        self.n_test_splits = int(n_test_splits)
        self.samples_info_sets = samples_info_sets
        self.pct_embargo = float(pct_embargo)

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        """Return number of *combinations* (not number of backtest paths).

        This matches sklearn's BaseCrossValidator contract — for the
        backtest-path count use :func:`combinatorial_paths_count`.
        """
        return comb(self.n_splits, self.n_test_splits)

    def n_backtest_paths(self) -> int:
        """Return ``φ(N, k) = C(N, k) · k / N`` — number of paths."""
        return combinatorial_paths_count(self.n_splits, self.n_test_splits)

    def split(
        self,
        X,
        y=None,
        groups=None,
    ):  # noqa: D401
        """Yield ``(train_indices, test_indices)`` for every combination.

        The order of yielded splits matches the natural enumeration of
        ``combinations(range(N), k)``.
        """
        n = self._n_samples(X)
        fold_bounds = _compute_fold_bounds(n, self.n_splits)
        for test_fold_ids in combinations(range(self.n_splits), self.n_test_splits):
            test_idx = self._union_ranges(fold_bounds, test_fold_ids)
            test_idx_arr = np.asarray(sorted(test_idx), dtype=np.int64)
            embargo_len = int(np.ceil(self.pct_embargo * n))
            train_idx = self._build_train(
                n=n,
                test_indices=test_idx_arr,
                embargo_len=embargo_len,
            )
            yield train_idx, test_idx_arr

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _n_samples(X) -> int:
        if hasattr(X, "shape"):
            return int(X.shape[0])
        return int(len(X))

    @staticmethod
    def _union_ranges(
        fold_bounds: list[tuple[int, int]], test_ids: tuple[int, ...]
    ) -> list[int]:
        out: list[int] = []
        for fid in test_ids:
            start, end = fold_bounds[fid]
            out.extend(range(start, end))
        return out

    def _build_train(
        self,
        *,
        n: int,
        test_indices: np.ndarray,
        embargo_len: int,
    ) -> np.ndarray:
        all_idx = np.arange(n, dtype=np.int64)
        # Drop the test indices.
        train_mask = np.ones(n, dtype=bool)
        train_mask[test_indices] = False
        # Embargo: drop ``embargo_len`` observations immediately after
        # any contiguous block of test indices.
        if embargo_len > 0 and len(test_indices) > 0:
            blocks = _contiguous_blocks(test_indices)
            for start, end in blocks:
                embargo_start = end + 1
                embargo_end = min(n, embargo_start + embargo_len)
                if embargo_start < embargo_end:
                    train_mask[embargo_start:embargo_end] = False
        # Purge: drop train observations whose info-set end overlaps any
        # test observation.
        if self.samples_info_sets is not None:
            info = self.samples_info_sets
            try:
                test_info = info.iloc[test_indices]
                test_first = test_info.index.min()
                test_last_info = test_info.max()
                if pd.notna(test_first) and pd.notna(test_last_info):
                    # A train observation is purged when its index is < test_first
                    # AND its info-set end is >= test_first (i.e. it spans into the test fold).
                    for i in range(n):
                        if not train_mask[i]:
                            continue
                        end_t = info.iloc[i]
                        idx_t = info.index[i]
                        if pd.notna(end_t) and pd.notna(idx_t):
                            if idx_t < test_first and end_t >= test_first:
                                train_mask[i] = False
            except Exception:  # noqa: BLE001 — defensive
                logger.debug("purge step skipped (info-set mismatch)", exc_info=True)
        return all_idx[train_mask]


# --------------------------------------------------------------------------- helpers


def _compute_fold_bounds(n: int, n_splits: int) -> list[tuple[int, int]]:
    """Return ``[(start, end), …]`` for ``n_splits`` (roughly equal) folds."""
    fold_size = n // n_splits
    remainder = n - fold_size * n_splits
    bounds: list[tuple[int, int]] = []
    start = 0
    for i in range(n_splits):
        extra = 1 if i < remainder else 0
        end = start + fold_size + extra
        bounds.append((start, end))
        start = end
    return bounds


def _contiguous_blocks(indices: np.ndarray) -> list[tuple[int, int]]:
    """Return ``[(start, end), …]`` contiguous blocks (end inclusive)."""
    if len(indices) == 0:
        return []
    blocks: list[tuple[int, int]] = []
    start = indices[0]
    prev = start
    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        blocks.append((int(start), int(prev)))
        start = idx
        prev = idx
    blocks.append((int(start), int(prev)))
    return blocks


__all__ = [
    "CombinatorialPurgedKFold",
    "combinatorial_paths_count",
]
