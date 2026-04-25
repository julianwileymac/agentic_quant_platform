"""Split planning helpers for deterministic ML train/valid/test reuse."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.data.cv import PurgedKFold, TimeSeriesWalkForward


@dataclass
class PlannedSplit:
    """Canonical split artifact payload persisted in ``split_artifacts``."""

    fold_name: str
    segment: str
    start_time: datetime | None
    end_time: datetime | None
    indices: list[int]
    meta: dict[str, Any]


def build_split_plan(
    frame: pd.DataFrame,
    *,
    method: str,
    config: dict[str, Any],
    date_column: str = "timestamp",
) -> tuple[list[PlannedSplit], dict[str, list[str]]]:
    """Materialize deterministic split artifacts from a bar panel."""
    df = _prepare_frame(frame, date_column=date_column)
    if df.empty:
        raise ValueError("split planner received an empty frame")

    method_key = str(method or "fixed").strip().lower()
    if method_key == "fixed":
        artifacts, segments = _fixed_splits(df, config=config, date_column=date_column)
    elif method_key in {"purged_kfold", "purged-kfold", "kfold"}:
        artifacts, segments = _purged_kfold_splits(df, config=config, date_column=date_column)
    elif method_key in {"walk_forward", "walk-forward"}:
        artifacts, segments = _walk_forward_splits(df, config=config, date_column=date_column)
    else:
        raise ValueError(f"unsupported split method: {method!r}")
    return artifacts, segments


def artifacts_to_segments(
    artifacts: list[dict[str, Any]] | list[PlannedSplit],
    *,
    fold_name: str = "default",
) -> dict[str, list[str]]:
    """Convert persisted artifacts into DatasetH ``segments`` mapping."""
    out: dict[str, list[str]] = {}
    for raw in artifacts:
        row = raw if isinstance(raw, PlannedSplit) else PlannedSplit(**raw)
        if row.fold_name != fold_name:
            continue
        if row.segment not in {"train", "valid", "test", "infer"}:
            continue
        start = _to_iso(row.start_time)
        end = _to_iso(row.end_time)
        if start is None or end is None:
            continue
        out[row.segment] = [start, end]

    # Keep downstream contracts stable.
    if "test" in out and "infer" not in out:
        out["infer"] = list(out["test"])
    return out


def _fixed_splits(
    df: pd.DataFrame,
    *,
    config: dict[str, Any],
    date_column: str,
) -> tuple[list[PlannedSplit], dict[str, list[str]]]:
    segments = dict(config.get("segments") or {})
    if not segments:
        segments = _segments_from_ratios(df, config=config, date_column=date_column)

    artifacts: list[PlannedSplit] = []
    out_segments: dict[str, list[str]] = {}
    for segment in ("train", "valid", "test"):
        if segment not in segments:
            continue
        start_raw, end_raw = _segment_bounds(segments[segment])
        mask = (df[date_column] >= start_raw) & (df[date_column] <= end_raw)
        idx = df.index[mask].to_numpy(dtype=int)
        if len(idx) == 0:
            continue
        start_time = _to_dt(df.loc[idx[0], date_column])
        end_time = _to_dt(df.loc[idx[-1], date_column])
        artifacts.append(
            PlannedSplit(
                fold_name="default",
                segment=segment,
                start_time=start_time,
                end_time=end_time,
                indices=_indices_to_list(idx),
                meta={"method": "fixed", "n_rows": int(len(idx))},
            )
        )
        out_segments[segment] = [_to_iso(start_time), _to_iso(end_time)]  # type: ignore[list-item]
    if "test" in out_segments and "infer" not in out_segments:
        out_segments["infer"] = list(out_segments["test"])
    return artifacts, out_segments


def _purged_kfold_splits(
    df: pd.DataFrame,
    *,
    config: dict[str, Any],
    date_column: str,
) -> tuple[list[PlannedSplit], dict[str, list[str]]]:
    splitter = PurgedKFold(
        n_splits=int(config.get("n_splits", 5)),
        embargo_days=int(config.get("embargo_days", 1)),
        date_column=date_column,
    )
    artifacts: list[PlannedSplit] = []
    first_fold: dict[str, list[str]] = {}
    for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(df)):
        fold_name = f"fold_{fold_idx}"
        train_art = _indices_split(
            df,
            date_column=date_column,
            fold_name=fold_name,
            segment="train",
            indices=np.asarray(train_idx),
            meta={"method": "purged_kfold"},
        )
        test_art = _indices_split(
            df,
            date_column=date_column,
            fold_name=fold_name,
            segment="test",
            indices=np.asarray(test_idx),
            meta={"method": "purged_kfold"},
        )
        artifacts.extend([train_art, test_art])
        if fold_idx == 0:
            first_fold = {
                "train": [_to_iso(train_art.start_time), _to_iso(train_art.end_time)],  # type: ignore[list-item]
                "test": [_to_iso(test_art.start_time), _to_iso(test_art.end_time)],  # type: ignore[list-item]
            }
    if "test" in first_fold:
        first_fold["infer"] = list(first_fold["test"])
    return artifacts, first_fold


def _walk_forward_splits(
    df: pd.DataFrame,
    *,
    config: dict[str, Any],
    date_column: str,
) -> tuple[list[PlannedSplit], dict[str, list[str]]]:
    splitter = TimeSeriesWalkForward(
        window_days=int(config.get("window_days", 252)),
        step_days=int(config.get("step_days", 63)),
        min_train_days=int(config.get("min_train_days", 252)),
        date_column=date_column,
        mode=str(config.get("mode", "rolling")),
    )
    artifacts: list[PlannedSplit] = []
    first_fold: dict[str, list[str]] = {}
    for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(df)):
        fold_name = f"fold_{fold_idx}"
        train_art = _indices_split(
            df,
            date_column=date_column,
            fold_name=fold_name,
            segment="train",
            indices=np.asarray(train_idx),
            meta={"method": "walk_forward"},
        )
        test_art = _indices_split(
            df,
            date_column=date_column,
            fold_name=fold_name,
            segment="test",
            indices=np.asarray(test_idx),
            meta={"method": "walk_forward"},
        )
        artifacts.extend([train_art, test_art])
        if fold_idx == 0:
            first_fold = {
                "train": [_to_iso(train_art.start_time), _to_iso(train_art.end_time)],  # type: ignore[list-item]
                "test": [_to_iso(test_art.start_time), _to_iso(test_art.end_time)],  # type: ignore[list-item]
            }
    if "test" in first_fold:
        first_fold["infer"] = list(first_fold["test"])
    return artifacts, first_fold


def _prepare_frame(frame: pd.DataFrame, *, date_column: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy().reset_index(drop=True)
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df = df.dropna(subset=[date_column]).sort_values(date_column).reset_index(drop=True)
    return df


def _segment_bounds(spec: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return pd.Timestamp(spec[0]), pd.Timestamp(spec[1])
    raise ValueError(f"invalid segment bounds: {spec!r}")


def _segments_from_ratios(
    df: pd.DataFrame,
    *,
    config: dict[str, Any],
    date_column: str,
) -> dict[str, list[str]]:
    train_ratio = float(config.get("train_ratio", 0.7))
    valid_ratio = float(config.get("valid_ratio", 0.15))
    total = len(df)
    train_end = max(1, int(total * train_ratio))
    valid_end = max(train_end + 1, int(total * (train_ratio + valid_ratio)))
    train_ts = (df.loc[0, date_column], df.loc[train_end - 1, date_column])
    valid_ts = (df.loc[train_end, date_column], df.loc[min(valid_end - 1, total - 1), date_column])
    test_ts = (df.loc[min(valid_end, total - 1), date_column], df.loc[total - 1, date_column])
    return {
        "train": [_to_iso(train_ts[0]), _to_iso(train_ts[1])],  # type: ignore[list-item]
        "valid": [_to_iso(valid_ts[0]), _to_iso(valid_ts[1])],  # type: ignore[list-item]
        "test": [_to_iso(test_ts[0]), _to_iso(test_ts[1])],  # type: ignore[list-item]
    }


def _indices_split(
    df: pd.DataFrame,
    *,
    date_column: str,
    fold_name: str,
    segment: str,
    indices: np.ndarray,
    meta: dict[str, Any],
) -> PlannedSplit:
    idx = np.asarray(indices, dtype=int)
    if len(idx) == 0:
        return PlannedSplit(
            fold_name=fold_name,
            segment=segment,
            start_time=None,
            end_time=None,
            indices=[],
            meta={**meta, "n_rows": 0},
        )
    start_time = _to_dt(df.loc[idx[0], date_column])
    end_time = _to_dt(df.loc[idx[-1], date_column])
    return PlannedSplit(
        fold_name=fold_name,
        segment=segment,
        start_time=start_time,
        end_time=end_time,
        indices=_indices_to_list(idx),
        meta={**meta, "n_rows": int(len(idx))},
    )


def _indices_to_list(indices: np.ndarray) -> list[int]:
    return [int(i) for i in np.asarray(indices, dtype=int).tolist()]


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
