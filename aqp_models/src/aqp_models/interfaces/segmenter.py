"""Segmenter — structural-break / regime-change detector.

The report's fourth reference application: detect points in a
non-stationary financial time series where the underlying statistical
properties shift (mean, variance, autocorrelation). Used by agents to
localise regime windows for follow-up training or analysis.

Backed by either:

- a native segmenter that exposes ``segment(series) -> list[int]``, or
- a "rolling z-score change" fallback that flags rows whose
  z-score against the previous window exceeds a configured threshold.
  The fallback gives agents a deterministic baseline when no native
  segmenter is wired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp_models.interfaces.base import InterfaceMetadata, PolymorphicInterface


@dataclass(slots=True)
class SegmentBoundary:
    """One structural break detected by :meth:`Segmenter.segment`."""

    index: int
    label: str = ""
    score: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "index": int(self.index),
            "label": self.label,
            "score": float(self.score),
            "extras": dict(self.extras),
        }


@register("Segmenter", kind="interface")
class Segmenter(PolymorphicInterface):
    """Polymorphic wrapper for structural-break detectors."""

    interface_kind = "segmenter"
    alias = "segmenter"

    def __init__(
        self,
        *,
        model: Any,
        alias: str | None = None,
        window: int = 30,
        threshold: float = 3.0,
    ) -> None:
        super().__init__(model=model, alias=alias)
        self._window = max(int(window), 2)
        self._threshold = float(threshold)

    def segment(
        self,
        series: pd.Series | np.ndarray | list[float],
        **kwargs: Any,
    ) -> tuple[list[SegmentBoundary], InterfaceMetadata]:
        started = datetime.utcnow()
        arr = _coerce_series(series)

        if hasattr(self.model, "segment"):
            raw = self.model.segment(arr, **kwargs)
            boundaries = _coerce_boundaries(raw)
            strategy = "native_segment"
        else:
            boundaries = _rolling_zscore_breaks(
                arr, window=self._window, threshold=self._threshold
            )
            strategy = "rolling_zscore"

        metadata = self._build_metadata(
            started=started,
            extras={
                "strategy": strategy,
                "n_breaks": len(boundaries),
                "window": self._window,
                "threshold": self._threshold,
            },
        )
        return boundaries, metadata

    def supports(self, model: Any) -> bool:
        return hasattr(model, "segment") or hasattr(model, "predict")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_series(series: Any) -> np.ndarray:
    if isinstance(series, pd.Series):
        return series.to_numpy(dtype=float)
    arr = np.asarray(series, dtype=float).reshape(-1)
    return arr


def _coerce_boundaries(raw: Any) -> list[SegmentBoundary]:
    out: list[SegmentBoundary] = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, SegmentBoundary):
                out.append(item)
                continue
            if isinstance(item, dict):
                out.append(
                    SegmentBoundary(
                        index=int(item.get("index", item.get("idx", 0))),
                        label=str(item.get("label", "")),
                        score=float(item.get("score", 0.0)),
                        extras={
                            k: v
                            for k, v in item.items()
                            if k not in {"index", "idx", "label", "score"}
                        },
                    )
                )
                continue
            out.append(SegmentBoundary(index=int(item)))
    elif isinstance(raw, np.ndarray):
        for i in raw.reshape(-1).tolist():
            out.append(SegmentBoundary(index=int(i)))
    return out


def _rolling_zscore_breaks(
    arr: np.ndarray, *, window: int, threshold: float
) -> list[SegmentBoundary]:
    """Deterministic fallback: flag rows whose abs z-score crosses the gate."""
    if arr.size < window + 2:
        return []
    out: list[SegmentBoundary] = []
    for i in range(window, arr.size):
        ref = arr[i - window:i]
        mu = float(np.nanmean(ref))
        sigma = float(np.nanstd(ref))
        if sigma <= 0:
            continue
        z = float((arr[i] - mu) / sigma)
        if abs(z) >= threshold:
            out.append(
                SegmentBoundary(
                    index=int(i),
                    label="zscore_break",
                    score=abs(z),
                    extras={"mean": mu, "std": sigma, "z": z},
                )
            )
    return out


__all__ = ["SegmentBoundary", "Segmenter"]
