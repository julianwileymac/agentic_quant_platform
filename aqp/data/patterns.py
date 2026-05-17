"""Swing extrema + chart pattern detection.

Source: ``inspiration/analyzingalpha-master/2020-04-18-algorithmic-chart-pattern-detection/``
(``extrema.py`` + ``pattern-recognition.py``).

All functions are vectorised pandas / numpy. They emit pattern markers
indexed at the bar where the pattern *completes* (not where it began),
so they are usable as point-in-time signals without lookahead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Swing extrema
# ---------------------------------------------------------------------------


def find_swing_highs(close: pd.Series, window: int = 5) -> pd.Series:
    """Boolean series flagging local maxima within ``2*window+1`` bars."""
    rolling_max = close.rolling(2 * window + 1, center=True).max()
    return (close == rolling_max).fillna(False)


def find_swing_lows(close: pd.Series, window: int = 5) -> pd.Series:
    """Boolean series flagging local minima within ``2*window+1`` bars."""
    rolling_min = close.rolling(2 * window + 1, center=True).min()
    return (close == rolling_min).fillna(False)


# ---------------------------------------------------------------------------
# Chart patterns
# ---------------------------------------------------------------------------


@dataclass
class PatternDetection:
    timestamp: pd.Timestamp
    pattern: Literal["double_top", "double_bottom", "head_and_shoulders", "inverse_head_and_shoulders"]
    score: float
    extras: dict[str, float]


def detect_double_top(
    close: pd.Series,
    window: int = 5,
    tolerance: float = 0.02,
    min_separation: int = 5,
) -> list[PatternDetection]:
    """Find double-top patterns.

    A double top is two consecutive swing highs of approximately equal
    height (within ``tolerance``), separated by at least ``min_separation``
    bars and a notable trough between them.
    """
    highs = close[find_swing_highs(close, window)]
    if len(highs) < 2:
        return []
    detections: list[PatternDetection] = []
    arr = highs.to_numpy()
    idx = highs.index
    for i in range(1, len(arr)):
        a, b = arr[i - 1], arr[i]
        sep = (idx[i] - idx[i - 1]).days if hasattr(idx[i] - idx[i - 1], "days") else (idx[i] - idx[i - 1])
        if sep < min_separation:
            continue
        if abs(b - a) / max(a, b) <= tolerance:
            trough = close.loc[idx[i - 1] : idx[i]].min()
            score = float((min(a, b) - trough) / min(a, b))
            detections.append(
                PatternDetection(
                    timestamp=idx[i],
                    pattern="double_top",
                    score=score,
                    extras={"top_a": float(a), "top_b": float(b), "trough": float(trough)},
                )
            )
    return detections


def detect_double_bottom(
    close: pd.Series,
    window: int = 5,
    tolerance: float = 0.02,
    min_separation: int = 5,
) -> list[PatternDetection]:
    """Mirror of :func:`detect_double_top` — two consecutive equal swing lows."""
    lows = close[find_swing_lows(close, window)]
    if len(lows) < 2:
        return []
    detections: list[PatternDetection] = []
    arr = lows.to_numpy()
    idx = lows.index
    for i in range(1, len(arr)):
        a, b = arr[i - 1], arr[i]
        sep = (idx[i] - idx[i - 1]).days if hasattr(idx[i] - idx[i - 1], "days") else (idx[i] - idx[i - 1])
        if sep < min_separation:
            continue
        if abs(b - a) / max(a, b) <= tolerance:
            peak = close.loc[idx[i - 1] : idx[i]].max()
            score = float((peak - max(a, b)) / max(a, b))
            detections.append(
                PatternDetection(
                    timestamp=idx[i],
                    pattern="double_bottom",
                    score=score,
                    extras={"bottom_a": float(a), "bottom_b": float(b), "peak": float(peak)},
                )
            )
    return detections


def detect_head_and_shoulders(
    close: pd.Series,
    window: int = 5,
    shoulder_tolerance: float = 0.05,
) -> list[PatternDetection]:
    """Three-peak head and shoulders.

    Peaks are: shoulder, head (taller), shoulder (similar to first within
    ``shoulder_tolerance``).
    """
    highs = close[find_swing_highs(close, window)]
    if len(highs) < 3:
        return []
    arr = highs.to_numpy()
    idx = highs.index
    detections: list[PatternDetection] = []
    for i in range(2, len(arr)):
        l, h, r = arr[i - 2], arr[i - 1], arr[i]
        if h > l and h > r and abs(l - r) / max(l, r) <= shoulder_tolerance:
            detections.append(
                PatternDetection(
                    timestamp=idx[i],
                    pattern="head_and_shoulders",
                    score=float((h - max(l, r)) / max(l, r)),
                    extras={"left_shoulder": float(l), "head": float(h), "right_shoulder": float(r)},
                )
            )
    return detections


def detect_inverse_head_and_shoulders(
    close: pd.Series,
    window: int = 5,
    shoulder_tolerance: float = 0.05,
) -> list[PatternDetection]:
    """Three-trough inverted head and shoulders (bullish reversal)."""
    lows = close[find_swing_lows(close, window)]
    if len(lows) < 3:
        return []
    arr = lows.to_numpy()
    idx = lows.index
    detections: list[PatternDetection] = []
    for i in range(2, len(arr)):
        l, h, r = arr[i - 2], arr[i - 1], arr[i]
        if h < l and h < r and abs(l - r) / max(l, r) <= shoulder_tolerance:
            detections.append(
                PatternDetection(
                    timestamp=idx[i],
                    pattern="inverse_head_and_shoulders",
                    score=float((min(l, r) - h) / min(l, r)),
                    extras={"left_shoulder": float(l), "head": float(h), "right_shoulder": float(r)},
                )
            )
    return detections


def detect_all(
    close: pd.Series,
    window: int = 5,
    tolerance: float = 0.02,
    shoulder_tolerance: float = 0.05,
) -> list[PatternDetection]:
    """Run every pattern detector and return results sorted by timestamp."""
    out: list[PatternDetection] = []
    out += detect_double_top(close, window, tolerance)
    out += detect_double_bottom(close, window, tolerance)
    out += detect_head_and_shoulders(close, window, shoulder_tolerance)
    out += detect_inverse_head_and_shoulders(close, window, shoulder_tolerance)
    out.sort(key=lambda d: d.timestamp)
    return out


__all__ = [
    "PatternDetection",
    "detect_all",
    "detect_double_bottom",
    "detect_double_top",
    "detect_head_and_shoulders",
    "detect_inverse_head_and_shoulders",
    "find_swing_highs",
    "find_swing_lows",
]
