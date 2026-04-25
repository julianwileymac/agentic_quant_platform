"""Shared helpers for the ML model zoo.

Every concrete model consumes either a :class:`aqp.ml.dataset.DatasetH`
(panel data) or a :class:`aqp.ml.dataset.TSDatasetH` (time-series samples).
This module centralises the ``(X, y)`` extraction so the model files don't
repeat the same boilerplate.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.handler import DK_I, DK_L


def prepare_panel(
    dataset: Any,
    segment: str = "train",
    *,
    data_key: str = DK_L,
) -> pd.DataFrame:
    """Return a flat panel for training. Returns a DataFrame with a
    ``(timestamp, vt_symbol)`` MultiIndex and MultiIndex columns
    ``(feature|label, name)``."""
    try:
        df = dataset.prepare(segment, col_set="__all__", data_key=data_key)
    except TypeError:
        df = dataset.prepare(segment)
    if isinstance(df, list):
        df = df[0]
    if not isinstance(df.index, pd.MultiIndex):
        # Best-effort rebuild.
        if "timestamp" in df.columns and "vt_symbol" in df.columns:
            df = df.set_index(["timestamp", "vt_symbol"]).sort_index()
    return df


def split_xy(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Break a prepared panel into ``(X, y, feature_names)``.

    Features live under the ``feature`` multi-index; labels under ``label``.
    When columns are not MultiIndex, we fall back to treating every
    non-``LABEL`` column as a feature.
    """
    if isinstance(panel.columns, pd.MultiIndex):
        feature_block = panel["feature"] if "feature" in panel.columns.get_level_values(0) else panel
        label_block = panel["label"] if "label" in panel.columns.get_level_values(0) else None
    else:
        label_cols = [c for c in panel.columns if str(c).upper().startswith("LABEL")]
        feature_block = panel.drop(columns=label_cols)
        label_block = panel[label_cols] if label_cols else None
    feature_cols = list(feature_block.columns)
    X = feature_block.to_numpy(dtype=np.float32, na_value=0.0)
    if label_block is None or label_block.empty:
        y = np.zeros(len(panel), dtype=np.float32)
    else:
        y = label_block.iloc[:, 0].to_numpy(dtype=np.float32, na_value=0.0)
    return X, y, [str(c) for c in feature_cols]


def predict_to_series(
    dataset: Any,
    segment: str,
    preds: np.ndarray,
    *,
    data_key: str = DK_I,
) -> pd.Series:
    """Wrap a raw prediction array in a ``(datetime, vt_symbol)`` Series."""
    panel = prepare_panel(dataset, segment, data_key=data_key)
    if len(panel) == 0:
        return pd.Series(dtype=float)
    if len(preds) != len(panel):
        preds = preds[: len(panel)]
    if isinstance(panel.index, pd.MultiIndex):
        idx = panel.index
    else:
        idx = pd.MultiIndex.from_arrays(
            [pd.to_datetime(panel.get("timestamp")), panel.get("vt_symbol")],
            names=["datetime", "vt_symbol"],
        )
    return pd.Series(preds, index=idx, name="score")


__all__ = ["prepare_panel", "predict_to_series", "split_xy"]
