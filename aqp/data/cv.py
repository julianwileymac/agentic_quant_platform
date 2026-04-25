"""Time-aware cross-validation helpers (ML4T playbook).

Two strategies for avoiding lookahead leakage on panel data:

- :class:`MultipleTimeSeriesCV` — the book's canonical rolling
  train/test split on a multi-indexed ``(ticker, date)`` frame.
- :class:`PurgedKFold` — K-fold split with a configurable *embargo* to
  prevent the training window from ending too close to the test window
  (Lopez de Prado's *Advances in Financial ML*).

Also included: :class:`TimeSeriesWalkForward` for a simpler
train-then-test windowed split.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# MultipleTimeSeriesCV (ML4T utils.py port)
# ---------------------------------------------------------------------------


@dataclass
class MultipleTimeSeriesCV:
    """Rolling train/test splits over a panel indexed by ``(ticker, date)``.

    Translated from ``utils.MultipleTimeSeriesCV`` in the ML4T book
    repository (BSD-3). Given an ``n_splits``, generate (train, test)
    index pairs that each consume ``train_period_length`` dates for
    training and ``test_period_length`` dates for testing, slid
    backwards from the end of the panel by ``test_period_length`` on
    each split.

    ``lookahead`` places an embargo (in days) between the train and test
    windows to avoid label leakage for forecast horizons > 1.
    """

    n_splits: int = 3
    train_period_length: int = 252
    test_period_length: int = 63
    lookahead: int = 1
    date_idx: str = "date"
    shuffle: bool = False

    def split(self, X: pd.DataFrame, y: pd.Series | None = None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        unique_dates = X.index.get_level_values(self.date_idx).unique()
        days = sorted(unique_dates, reverse=True)
        split_idx: list[tuple[int, int, int, int]] = []
        for i in range(self.n_splits):
            test_end_idx = i * self.test_period_length
            test_start_idx = test_end_idx + self.test_period_length
            train_end_idx = test_start_idx + self.lookahead - 1
            train_start_idx = train_end_idx + self.train_period_length + self.lookahead - 1
            split_idx.append((train_start_idx, train_end_idx, test_start_idx, test_end_idx))

        dates = X.reset_index()[[self.date_idx]]
        for train_start, train_end, test_start, test_end in split_idx:
            train_idx = dates[
                (dates[self.date_idx] > days[min(train_start, len(days) - 1)])
                & (dates[self.date_idx] <= days[min(train_end, len(days) - 1)])
            ].index
            test_idx = dates[
                (dates[self.date_idx] > days[min(test_start, len(days) - 1)])
                & (dates[self.date_idx] <= days[min(test_end, len(days) - 1)])
            ].index
            if self.shuffle:
                np.random.shuffle(train_idx.values)
            yield train_idx.values, test_idx.values

    def get_n_splits(self, X: pd.DataFrame | None = None, y=None, groups=None) -> int:
        return self.n_splits


# ---------------------------------------------------------------------------
# PurgedKFold (Lopez de Prado)
# ---------------------------------------------------------------------------


@dataclass
class PurgedKFold:
    """K-fold split with an embargo gap between train and test.

    Sorts a time-indexed frame, chops into ``n_splits`` contiguous test
    folds, and removes rows within ``embargo_days`` of the test boundary
    from the training set.
    """

    n_splits: int = 5
    embargo_days: int = 1
    date_column: str = "timestamp"

    def split(self, X: pd.DataFrame, y: pd.Series | None = None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        df = X.reset_index(drop=True).copy()
        df[self.date_column] = pd.to_datetime(df[self.date_column])
        df = df.sort_values(self.date_column)
        fold_size = max(1, len(df) // self.n_splits)
        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = test_start + fold_size if i < self.n_splits - 1 else len(df)
            test_idx = df.iloc[test_start:test_end].index
            embargo = pd.Timedelta(days=self.embargo_days)
            lo_ts = df.iloc[test_start][self.date_column] - embargo
            hi_ts = df.iloc[test_end - 1][self.date_column] + embargo
            train_mask = (df[self.date_column] < lo_ts) | (df[self.date_column] > hi_ts)
            train_idx = df.loc[train_mask].index
            yield train_idx.to_numpy(), test_idx.to_numpy()

    def get_n_splits(self, X: pd.DataFrame | None = None, y=None, groups=None) -> int:
        return self.n_splits


# ---------------------------------------------------------------------------
# Walk-forward (simpler)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CombinatorialPurgedCV (Lopez de Prado, AFML ch. 12)
# ---------------------------------------------------------------------------


@dataclass
class CombinatorialPurgedCV:
    """Combinatorial purged cross-validation (CPCV).

    Generates ``C(n_splits, n_test_splits)`` train/test pairs by cutting
    the sample into ``n_splits`` disjoint groups and enumerating every
    combination of ``n_test_splits`` groups as test sets. Rows within
    ``embargo_days`` of any test group are dropped from the train set,
    matching the classic purge semantics.

    Preferred over plain :class:`PurgedKFold` when doing backtest-paths
    analysis — CPCV delivers many more train/test combinations per panel
    so overfitting statistics are more stable.
    """

    n_splits: int = 6
    n_test_splits: int = 2
    embargo_days: int = 1
    date_column: str = "timestamp"

    def split(self, X: pd.DataFrame, y: pd.Series | None = None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        from itertools import combinations

        df = X.reset_index(drop=True).copy()
        df[self.date_column] = pd.to_datetime(df[self.date_column])
        df = df.sort_values(self.date_column)
        fold_size = max(1, len(df) // self.n_splits)

        splits: list[tuple[int, int]] = []
        for i in range(self.n_splits):
            start = i * fold_size
            end = start + fold_size if i < self.n_splits - 1 else len(df)
            splits.append((start, end))

        embargo = pd.Timedelta(days=self.embargo_days)
        for combo in combinations(range(self.n_splits), self.n_test_splits):
            test_indices: list[int] = []
            test_bounds: list[tuple[pd.Timestamp, pd.Timestamp]] = []
            for c in combo:
                s, e = splits[c]
                block = df.iloc[s:e]
                if block.empty:
                    continue
                test_indices.extend(block.index.tolist())
                test_bounds.append((block[self.date_column].iloc[0], block[self.date_column].iloc[-1]))
            if not test_indices:
                continue
            mask = pd.Series(True, index=df.index)
            for lo, hi in test_bounds:
                mask &= ~((df[self.date_column] >= lo - embargo) & (df[self.date_column] <= hi + embargo))
            train_idx = df.loc[mask].index.to_numpy()
            yield train_idx, np.asarray(test_indices)

    def get_n_splits(self, X: pd.DataFrame | None = None, y=None, groups=None) -> int:
        from math import comb

        return comb(self.n_splits, self.n_test_splits)


@dataclass
class TimeSeriesWalkForward:
    """Expanding/rolling walk-forward splits on a sorted time-indexed frame."""

    window_days: int = 252
    step_days: int = 63
    min_train_days: int = 252
    date_column: str = "timestamp"
    mode: str = "rolling"  # rolling | expanding

    def split(self, X: pd.DataFrame, y: pd.Series | None = None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        df = X.reset_index(drop=True).copy()
        df[self.date_column] = pd.to_datetime(df[self.date_column])
        df = df.sort_values(self.date_column).reset_index(drop=True)
        df["_idx"] = df.index
        dates = df[self.date_column]
        start_ts = dates.iloc[0]
        end_ts = dates.iloc[-1]
        cursor = start_ts + pd.Timedelta(days=self.min_train_days)
        while cursor < end_ts:
            test_end = min(cursor + pd.Timedelta(days=self.step_days), end_ts)
            if self.mode == "rolling":
                train_lo = max(start_ts, cursor - pd.Timedelta(days=self.window_days))
                train = df[(dates >= train_lo) & (dates < cursor)]
            else:  # expanding
                train = df[dates < cursor]
            test = df[(dates >= cursor) & (dates < test_end)]
            if not train.empty and not test.empty:
                yield train["_idx"].to_numpy(), test["_idx"].to_numpy()
            cursor = test_end

    def get_n_splits(self, X: pd.DataFrame | None = None, y=None, groups=None) -> int:
        return sum(1 for _ in self.split(X))
