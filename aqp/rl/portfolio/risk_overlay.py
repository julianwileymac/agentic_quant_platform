"""``f_R`` — hard-constraint risk overlay (final immutable safety layer).

The risk overlay is the last line of defence between the RL policy
and the broker. It truncates weights that violate portfolio
constraints — max position pct, max gross exposure, leverage caps,
illegal long-only negativity — before the weight vector is handed
off to :class:`TargetWeightsRebalancer` and the live execution path.

This module re-uses :class:`aqp.risk.limits.RiskLimits` so the same
constraint dataclass that governs the live paper-trading session
also governs offline RL training.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.rl.portfolio.pipeline import PipelineState

logger = logging.getLogger(__name__)


class RiskOverlay:
    """Base class for the ``f_R`` stage. Defaults to a no-op."""

    def apply(self, state: PipelineState) -> PipelineState:
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__}


class PositionCapRiskOverlay(RiskOverlay):
    """Clamp per-position absolute weight to ``max_position_pct``.

    Mirrors :attr:`aqp.risk.limits.RiskLimits.max_position_pct`. If the
    clamping renders any weight zero, the overlay sets
    ``state.context['truncated']`` to ``True`` so the matching
    ``RiskBreachTermination`` can fire — feeds the FinRL-X
    "stop properly" penalty in the reward shaping layer.
    """

    def __init__(self, *, max_position_pct: float = 0.30, mark_truncated: bool = False) -> None:
        self.max_position_pct = float(max_position_pct)
        self.mark_truncated = bool(mark_truncated)

    def apply(self, state: PipelineState) -> PipelineState:
        if state.weights is None:
            return state
        arr = np.asarray(state.weights, dtype=np.float64)
        clipped = np.clip(arr, -self.max_position_pct, self.max_position_pct)
        breached = bool(np.any(np.abs(arr) > self.max_position_pct + 1e-9))
        state.weights = clipped
        if breached:
            logger.debug(
                "PositionCapRiskOverlay clamped %d positions above %s",
                int(np.sum(np.abs(arr) > self.max_position_pct + 1e-9)),
                self.max_position_pct,
            )
            if self.mark_truncated:
                state.context = dict(state.context)
                state.context["truncated"] = True
                state.context.setdefault("risk_breach_reason", "position_cap_exceeded")
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "max_position_pct": self.max_position_pct,
            "mark_truncated": self.mark_truncated,
        }


class GrossExposureRiskOverlay(RiskOverlay):
    """Scale weights so ``sum(|w|) <= max_gross``.

    Mirrors :attr:`aqp.risk.limits.RiskLimits.max_gross_exposure`. Always
    scales (never truncates) so the relative weight composition is
    preserved.
    """

    def __init__(self, *, max_gross: float = 1.0, mark_truncated: bool = False) -> None:
        self.max_gross = float(max_gross)
        self.mark_truncated = bool(mark_truncated)

    def apply(self, state: PipelineState) -> PipelineState:
        if state.weights is None:
            return state
        arr = np.asarray(state.weights, dtype=np.float64)
        gross = float(np.abs(arr).sum())
        if gross <= self.max_gross + 1e-9 or gross <= 0:
            state.weights = arr
            return state
        scale = self.max_gross / gross
        state.weights = arr * scale
        logger.debug(
            "GrossExposureRiskOverlay scaled weights by %.4f (gross=%.4f > %.4f)",
            scale,
            gross,
            self.max_gross,
        )
        if self.mark_truncated:
            state.context = dict(state.context)
            state.context["truncated"] = True
            state.context.setdefault("risk_breach_reason", "gross_exposure_exceeded")
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "max_gross": self.max_gross,
            "mark_truncated": self.mark_truncated,
        }


class StackedRiskOverlay(RiskOverlay):
    """Chain multiple :class:`RiskOverlay` instances left-to-right.

    Order matters: position caps should fire before gross-exposure
    scaling so a single oversized position does not consume the
    entire gross budget through pure normalisation.
    """

    def __init__(self, *, overlays: list[RiskOverlay] | None = None) -> None:
        self.overlays: list[RiskOverlay] = list(overlays or [])

    def apply(self, state: PipelineState) -> PipelineState:
        for overlay in self.overlays:
            state = overlay.apply(state)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "overlays": [getattr(o, "to_dict", lambda: {"class": type(o).__name__})() for o in self.overlays],
        }


__all__ = [
    "GrossExposureRiskOverlay",
    "PositionCapRiskOverlay",
    "RiskOverlay",
    "StackedRiskOverlay",
]
