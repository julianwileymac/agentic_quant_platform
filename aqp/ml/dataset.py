"""Datasets — native ports of ``qlib.data.dataset.{Dataset, DatasetH, TSDatasetH}``.

A :class:`DatasetH` wraps a :class:`aqp.ml.handler.DataHandler` plus a
``segments`` dict mapping segment names (``train``/``valid``/``test`` or any
custom name) to either a slice of timestamps or a ``(start, end)`` pair. A
:class:`TSDatasetH` produces a :class:`TSDataSampler` whose ``__getitem__``
returns a ``(step_len, n_features)`` window for recurrent / attention
models.

Reference: ``inspiration/qlib-main/qlib/data/dataset/__init__.py``.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.base import Serializable
from aqp.ml.handler import CS_FEATURE, CS_LABEL, DK_I, DataHandler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base Dataset.
# ---------------------------------------------------------------------------


class Dataset(Serializable):
    """Minimal dataset contract — ``prepare(**kwargs)`` is the single access
    path. Subclasses can override ``config`` / ``setup_data`` as needed."""

    def config(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def setup_data(self) -> None:
        """Eager materialisation hook."""

    def prepare(self, **kwargs: Any) -> Any:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# DatasetH — handler + named segments.
# ---------------------------------------------------------------------------


class DatasetH(Dataset):
    """Handler-backed dataset with named time-range segments."""

    def __init__(
        self,
        handler: DataHandler | dict[str, Any],
        segments: Mapping[str, Any] | None = None,
        fetch_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        self.handler = _maybe_build_handler(handler)
        self.segments = dict(segments or {})
        self.fetch_kwargs = dict(fetch_kwargs or {})

    def setup_data(self) -> None:
        self.handler.setup_data()

    # ---- resolution ----------------------------------------------------

    def _resolve_selector(self, segment_name: str) -> slice:
        if segment_name not in self.segments:
            raise KeyError(f"Segment {segment_name!r} not in segments {list(self.segments)}")
        cut = self.segments[segment_name]
        if isinstance(cut, slice):
            return cut
        if isinstance(cut, (list, tuple)) and len(cut) == 2:
            start, end = cut
            return slice(pd.Timestamp(start) if start else None, pd.Timestamp(end) if end else None)
        raise ValueError(f"Unsupported segment spec: {cut!r}")

    def prepare(
        self,
        segments: str | list[str] | tuple[str, ...],
        col_set: str | list[str] = "__all__",
        data_key: str = DK_I,
        **kwargs: Any,
    ) -> pd.DataFrame | list[pd.DataFrame]:
        self.setup_data()

        def _one(name: str) -> pd.DataFrame:
            sel = self._resolve_selector(name)
            kw = {**self.fetch_kwargs, **kwargs}
            if isinstance(self.handler, DataHandler):
                try:
                    return self.handler.fetch(
                        selector=sel,
                        level="datetime",
                        col_set=col_set,
                        data_key=data_key,
                        **kw,
                    )
                except TypeError:
                    return self.handler.fetch(
                        selector=sel,
                        level="datetime",
                        col_set=col_set,
                        data_key=data_key,
                    )
            raise TypeError(f"Unsupported handler type: {type(self.handler).__name__}")

        if isinstance(segments, str):
            return _one(segments)
        return [_one(s) for s in segments]


# ---------------------------------------------------------------------------
# TSDataSampler — windowed array sampler for sequence models.
# ---------------------------------------------------------------------------


class TSDataSampler:
    """Produce ``(step_len, n_features)`` windows indexed by ``(date, symbol)``.

    Useful for LSTM/Transformer/TCN training loops that want batches of
    shape ``(batch, step_len, n_features)``.
    """

    def __init__(self, data: pd.DataFrame, step_len: int = 20) -> None:
        if data.empty:
            raise ValueError("TSDataSampler: empty data.")
        self.step_len = int(step_len)
        self._frame = data.sort_index()
        self._feature_cols = [c for c in data.columns if (not isinstance(c, tuple)) or c[0] == CS_FEATURE]
        self._label_col = next(
            (c for c in data.columns if isinstance(c, tuple) and c[0] == CS_LABEL),
            None,
        )
        self._index: list[tuple[pd.Timestamp, str]] = []
        for sym, sub in self._frame.groupby(level="vt_symbol" if isinstance(self._frame.index, pd.MultiIndex) else 0):
            for i in range(self.step_len - 1, len(sub)):
                ts = sub.index[i] if not isinstance(sub.index, pd.MultiIndex) else sub.index[i][0]
                self._index.append((ts, sym))

    def __len__(self) -> int:
        return len(self._index)

    def __getitem__(self, i: int) -> tuple[np.ndarray, float]:
        ts, sym = self._index[i]
        if isinstance(self._frame.index, pd.MultiIndex):
            sub = self._frame.loc[(slice(None, ts), sym)]
        else:
            sub = self._frame.loc[:ts]
        window = sub.iloc[-self.step_len:]
        x = window[self._feature_cols].to_numpy(dtype=np.float32)
        y = float("nan")
        if self._label_col is not None:
            try:
                y = float(window[self._label_col].iloc[-1])
            except Exception:
                y = float("nan")
        return x, y

    def get_index(self) -> pd.MultiIndex:
        return pd.MultiIndex.from_tuples(self._index, names=["datetime", "vt_symbol"])


# ---------------------------------------------------------------------------
# TSDatasetH — DatasetH that yields TSDataSampler instances.
# ---------------------------------------------------------------------------


class TSDatasetH(DatasetH):
    """DatasetH whose ``prepare`` returns :class:`TSDataSampler` objects."""

    def __init__(
        self,
        handler: DataHandler | dict[str, Any],
        segments: Mapping[str, Any] | None = None,
        step_len: int = 20,
        fetch_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(handler=handler, segments=segments, fetch_kwargs=fetch_kwargs)
        self.step_len = int(step_len)

    def prepare(
        self,
        segments: str | list[str] | tuple[str, ...],
        col_set: str | list[str] = "__all__",
        data_key: str = DK_I,
        **kwargs: Any,
    ) -> TSDataSampler | list[TSDataSampler]:
        if isinstance(segments, str):
            frame = super().prepare(segments, col_set=col_set, data_key=data_key, **kwargs)
            return TSDataSampler(frame, step_len=self.step_len)
        frames = super().prepare(segments, col_set=col_set, data_key=data_key, **kwargs)
        assert isinstance(frames, list)
        return [TSDataSampler(f, step_len=self.step_len) for f in frames]


def _maybe_build_handler(handler: DataHandler | dict[str, Any]) -> DataHandler:
    if isinstance(handler, DataHandler):
        return handler
    if isinstance(handler, dict) and "class" in handler:
        from aqp.core.registry import build_from_config

        built = build_from_config(handler)
        if not isinstance(built, DataHandler):
            raise TypeError(f"Expected DataHandler, got {type(built).__name__}")
        return built
    raise TypeError(f"Unsupported handler spec: {type(handler).__name__}")


def materialize_segments(
    artifacts: list[dict[str, Any]],
    *,
    fold_name: str = "default",
) -> dict[str, list[str]]:
    """Compatibility bridge from split artifacts to ``DatasetH.segments``."""
    from aqp.ml.planning import artifacts_to_segments

    return artifacts_to_segments(artifacts, fold_name=fold_name)


__all__ = [
    "Dataset",
    "DatasetH",
    "TSDataSampler",
    "TSDatasetH",
    "materialize_segments",
]
