"""Continuous futures curve construction.

Public surface for the Phase 1 (migration 0039) continuous-futures roll-stitching
module. The contract universe lives in :class:`aqp.persistence.models_instruments.InstrumentFuture`
rows; the curve snapshots live in :class:`aqp.persistence.models_macro.FuturesCurveRow`.
This package builds the stitched series an agent or backtest needs from those
two tables.
"""
from __future__ import annotations

from aqp.data.futures.curve import (
    DateBasedRoll,
    FuturesCurve,
    FuturesCurveSnapshot,
    OpenInterestRoll,
    RollEvent,
    RollRule,
    StitchedCurveRow,
    VolumeBasedRoll,
    list_curves,
    stitch_curve,
)

__all__ = [
    "DateBasedRoll",
    "FuturesCurve",
    "FuturesCurveSnapshot",
    "OpenInterestRoll",
    "RollEvent",
    "RollRule",
    "StitchedCurveRow",
    "VolumeBasedRoll",
    "list_curves",
    "stitch_curve",
]
