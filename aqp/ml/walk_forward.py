"""Walk-forward training adapter.

Mirrors ``akquant.ml`` ergonomics:
- ``WalkForwardSplitter`` produces ``(train_start, train_end, test_start,
  test_end)`` windows from a date index.
- ``WalkForwardTrainer`` calls a ``Model`` over each window and
  aggregates predictions.

Source: ``inspiration/akquant-main/examples/10_ml_walk_forward.py`` and
``pb_mock.py``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

import numpy as np
import pandas as pd

from aqp.ml.base import Model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    @property
    def train_slice(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.train_start, self.train_end

    @property
    def test_slice(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.test_start, self.test_end


class WalkForwardSplitter:
    """Generate non-overlapping walk-forward windows.

    Parameters:
        train_periods: number of periods in each training window.
        test_periods: number of periods in each test window.
        step_periods: how many periods to advance between windows.
            Defaults to ``test_periods`` (non-overlapping test sets).
        anchored: if True, training window grows; if False, it slides.
    """

    def __init__(
        self,
        train_periods: int = 252,
        test_periods: int = 21,
        step_periods: int | None = None,
        anchored: bool = False,
    ) -> None:
        self.train_periods = int(train_periods)
        self.test_periods = int(test_periods)
        self.step_periods = int(step_periods or test_periods)
        self.anchored = bool(anchored)

    def split(self, index: pd.DatetimeIndex) -> Iterator[WalkForwardWindow]:
        if not isinstance(index, pd.DatetimeIndex):
            index = pd.DatetimeIndex(index)
        n = len(index)
        if n < self.train_periods + self.test_periods:
            return
        train_start_pos = 0
        train_end_pos = self.train_periods - 1
        while train_end_pos + self.test_periods < n:
            test_start_pos = train_end_pos + 1
            test_end_pos = test_start_pos + self.test_periods - 1
            yield WalkForwardWindow(
                train_start=index[train_start_pos if not self.anchored else 0],
                train_end=index[train_end_pos],
                test_start=index[test_start_pos],
                test_end=index[test_end_pos],
            )
            train_end_pos += self.step_periods
            if not self.anchored:
                train_start_pos += self.step_periods


class _DatasetProtocol(Protocol):
    """Minimal contract a walk-forward-compatible dataset must satisfy."""

    def slice_dates(self, start: pd.Timestamp, end: pd.Timestamp) -> Any: ...


class WalkForwardTrainer:
    """Train a fresh copy of ``model_factory()`` on each walk-forward window.

    The dataset is expected to expose ``slice_dates(start, end)`` that
    returns a sub-dataset compatible with ``Model.fit`` / ``Model.predict``.
    For datasets that don't support slicing natively the caller can wrap
    them in :class:`SimpleSliceDataset` below.
    """

    def __init__(
        self,
        model_factory,
        splitter: WalkForwardSplitter,
        verbose: bool = False,
    ) -> None:
        self.model_factory = model_factory
        self.splitter = splitter
        self.verbose = verbose

    def fit_predict(self, dataset: _DatasetProtocol) -> pd.Series:
        """Train per window; return concatenated test-period predictions."""
        all_preds: list[pd.Series] = []
        for window in self.splitter.split(getattr(dataset, "index", pd.DatetimeIndex([]))):
            train_ds = dataset.slice_dates(window.train_start, window.train_end)
            test_ds = dataset.slice_dates(window.test_start, window.test_end)
            model: Model = self.model_factory()
            model.fit(train_ds)
            preds = model.predict(test_ds, segment="test")
            all_preds.append(preds)
            if self.verbose:
                logger.info(
                    "WF window %s..%s -> %s..%s n_preds=%s",
                    window.train_start, window.train_end,
                    window.test_start, window.test_end, len(preds),
                )
        if not all_preds:
            return pd.Series(dtype=float)
        return pd.concat(all_preds).sort_index()


@dataclass
class SimpleSliceDataset:
    """Minimal wrapper around a (features, labels) frame for walk-forward use.

    ``frame`` must be indexed by ``pd.DatetimeIndex``. ``label_col`` is the
    target column; remaining columns are features.
    """

    frame: pd.DataFrame
    label_col: str = "y"

    @property
    def index(self) -> pd.DatetimeIndex:
        idx = self.frame.index
        if isinstance(idx, pd.MultiIndex):
            idx = idx.get_level_values(0)
        return pd.DatetimeIndex(idx)

    def slice_dates(self, start: pd.Timestamp, end: pd.Timestamp) -> "SimpleSliceDataset":
        sub = self.frame.loc[start:end].copy()
        return SimpleSliceDataset(frame=sub, label_col=self.label_col)

    def features(self) -> pd.DataFrame:
        return self.frame.drop(columns=[self.label_col], errors="ignore")

    def labels(self) -> pd.Series:
        return self.frame[self.label_col]

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return self.features().to_numpy(), self.labels().to_numpy()


__all__ = [
    "SimpleSliceDataset",
    "WalkForwardSplitter",
    "WalkForwardTrainer",
    "WalkForwardWindow",
]
