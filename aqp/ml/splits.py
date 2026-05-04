"""Train/validation/test split helpers for tabular and panel data.

These helpers complement :mod:`aqp.ml.walk_forward` by exposing
ready-to-use train/validation/test patterns inspired by FinRL and
quant-trading examples.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class TrainValTestWindow:
    """A single rolling train/validation/test window."""

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp

    @property
    def train_slice(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.train_start, self.train_end

    @property
    def val_slice(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.val_start, self.val_end

    @property
    def test_slice(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.test_start, self.test_end


def _as_datetime_index(values: Iterable[pd.Timestamp] | pd.DatetimeIndex) -> pd.DatetimeIndex:
    if isinstance(values, pd.DatetimeIndex):
        idx = values
    else:
        idx = pd.DatetimeIndex(values)
    return pd.DatetimeIndex(idx).sort_values().unique()


def rolling_train_val_test_windows(
    index: Iterable[pd.Timestamp] | pd.DatetimeIndex,
    *,
    train_periods: int = 252,
    val_periods: int = 21,
    test_periods: int = 21,
    step_periods: int | None = None,
    anchored: bool = False,
) -> list[TrainValTestWindow]:
    """Generate rolling windows with explicit train/val/test spans."""
    idx = _as_datetime_index(index)
    n = len(idx)
    if n < train_periods + val_periods + test_periods:
        return []
    step = int(step_periods or test_periods)
    train_start_pos = 0
    train_end_pos = train_periods - 1
    out: list[TrainValTestWindow] = []
    while train_end_pos + val_periods + test_periods < n:
        val_start_pos = train_end_pos + 1
        val_end_pos = val_start_pos + val_periods - 1
        test_start_pos = val_end_pos + 1
        test_end_pos = test_start_pos + test_periods - 1
        out.append(
            TrainValTestWindow(
                train_start=idx[0 if anchored else train_start_pos],
                train_end=idx[train_end_pos],
                val_start=idx[val_start_pos],
                val_end=idx[val_end_pos],
                test_start=idx[test_start_pos],
                test_end=idx[test_end_pos],
            )
        )
        train_end_pos += step
        if not anchored:
            train_start_pos += step
    return out


def chronological_train_val_test_split(
    frame: pd.DataFrame,
    *,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    date_col: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Chronological row split without shuffling."""
    if frame.empty:
        return frame.copy(), frame.copy(), frame.copy()
    if train_ratio <= 0 or val_ratio <= 0 or train_ratio + val_ratio >= 1:
        raise ValueError("require 0 < train_ratio, val_ratio and train_ratio + val_ratio < 1")
    if date_col and date_col in frame.columns:
        sorted_frame = frame.assign(__aqp_ts=pd.to_datetime(frame[date_col], errors="coerce")).sort_values("__aqp_ts")
        sorted_frame = sorted_frame.drop(columns=["__aqp_ts"])
    else:
        sorted_frame = frame.sort_index()
    n = len(sorted_frame)
    train_n = max(1, int(n * train_ratio))
    val_n = max(1, int(n * val_ratio))
    if train_n + val_n >= n:
        val_n = max(1, n - train_n - 1)
    test_n = n - train_n - val_n
    if test_n <= 0:
        raise ValueError("dataset too small for requested train/val split ratios")
    train = sorted_frame.iloc[:train_n].copy()
    val = sorted_frame.iloc[train_n : train_n + val_n].copy()
    test = sorted_frame.iloc[train_n + val_n :].copy()
    return train, val, test


def quarterly_point_in_time_split(
    frame: pd.DataFrame,
    *,
    date_col: str = "datadate",
    inference_date: pd.Timestamp | str | None = None,
    train_quarters: int = 16,
    val_quarters: int = 4,
    frequency: str = "Q",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """FinRL-style quarter-bounded train/val/test split.

    - Train: historical quarters before validation window.
    - Validation: the ``val_quarters`` immediately before inference quarter.
    - Test: rows in the inference quarter only.
    """
    if frame.empty:
        return frame.copy(), frame.copy(), frame.copy()
    if date_col not in frame.columns:
        raise KeyError(f"{date_col!r} not found in frame")
    stamped = frame.copy()
    stamped[date_col] = pd.to_datetime(stamped[date_col], errors="coerce")
    stamped = stamped.dropna(subset=[date_col]).sort_values(date_col)
    if stamped.empty:
        return stamped.copy(), stamped.copy(), stamped.copy()
    periods = stamped[date_col].dt.to_period(frequency)
    unique_periods = sorted(periods.unique())
    if not unique_periods:
        return stamped.copy(), stamped.copy(), stamped.copy()

    infer_period = (
        pd.Timestamp(inference_date).to_period(frequency)
        if inference_date is not None
        else unique_periods[-1]
    )
    if infer_period not in unique_periods:
        infer_period = max((p for p in unique_periods if p <= infer_period), default=unique_periods[-1])

    infer_idx = unique_periods.index(infer_period)
    val_end_idx = max(-1, infer_idx - 1)
    val_start_idx = max(0, val_end_idx - int(val_quarters) + 1)
    train_end_idx = val_start_idx - 1
    train_start_idx = max(0, train_end_idx - int(train_quarters) + 1)

    train_periods = set(unique_periods[train_start_idx : train_end_idx + 1]) if train_end_idx >= train_start_idx else set()
    val_periods = set(unique_periods[val_start_idx : val_end_idx + 1]) if val_end_idx >= val_start_idx else set()

    train = stamped[periods.isin(train_periods)].copy()
    val = stamped[periods.isin(val_periods)].copy()
    test = stamped[periods == infer_period].copy()
    return train, val, test


__all__ = [
    "TrainValTestWindow",
    "chronological_train_val_test_split",
    "quarterly_point_in_time_split",
    "rolling_train_val_test_windows",
]
