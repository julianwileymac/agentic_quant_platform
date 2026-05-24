"""``f_T`` — timing adjustment / macro exposure scaling.

The timing module reads context-provided regime signals (turbulence,
VIX shocks, drawdown state) and uniformly scales the absolute market
exposure produced by ``f_A``. When a regime adverse event is
detected, ``f_T`` may dial gross exposure all the way to zero,
parking the portfolio in cash without changing relative weights.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from aqp_rl.portfolio.pipeline import PipelineState


class TimingAdjuster:
    """Base class for the ``f_T`` stage."""

    def adjust(self, state: PipelineState) -> PipelineState:
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__}


class ConstantTimingAdjuster(TimingAdjuster):
    """No-op timing adjuster (used for the FinRL-X default chain)."""

    def __init__(self, *, scale: float = 1.0) -> None:
        self.scale = float(scale)

    def adjust(self, state: PipelineState) -> PipelineState:
        if state.weights is None or self.scale == 1.0:
            return state
        state.weights = np.asarray(state.weights, dtype=np.float64) * float(self.scale)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "scale": self.scale}


class TurbulenceTimingAdjuster(TimingAdjuster):
    """Cut gross exposure when ``context['turbulence']`` exceeds a threshold.

    The decision is binary by default: above the threshold we apply
    ``cooldown_scale`` (default 0.0 = full risk-off); below we apply
    ``scale`` (default 1.0 = nominal exposure). For a smoother
    transition pass a ``smoothing`` value > 0 — the scale becomes
    ``scale * exp(-smoothing * max(0, turbulence - threshold))``.
    """

    def __init__(
        self,
        *,
        threshold: float = 140.0,
        scale: float = 1.0,
        cooldown_scale: float = 0.0,
        smoothing: float = 0.0,
    ) -> None:
        self.threshold = float(threshold)
        self.scale = float(scale)
        self.cooldown_scale = float(cooldown_scale)
        self.smoothing = float(smoothing)

    def adjust(self, state: PipelineState) -> PipelineState:
        if state.weights is None:
            return state
        turbulence = float(state.context.get("turbulence", 0.0) or 0.0)
        if turbulence <= self.threshold or self.smoothing > 0.0:
            if self.smoothing > 0.0 and turbulence > self.threshold:
                excess = turbulence - self.threshold
                effective = self.scale * float(np.exp(-self.smoothing * excess))
            else:
                effective = self.scale
        else:
            effective = self.cooldown_scale
        state.weights = np.asarray(state.weights, dtype=np.float64) * effective
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "threshold": self.threshold,
            "scale": self.scale,
            "cooldown_scale": self.cooldown_scale,
            "smoothing": self.smoothing,
        }


class VolatilityTargetingTimingAdjuster(TimingAdjuster):
    """Scale gross exposure so realised portfolio vol matches ``target_vol``.

    Reads ``context['portfolio_volatility']`` (annualised). If absent
    or zero the adjuster is a pass-through.
    """

    def __init__(self, *, target_vol: float = 0.10, max_scale: float = 2.0) -> None:
        self.target_vol = float(target_vol)
        self.max_scale = float(max_scale)

    def adjust(self, state: PipelineState) -> PipelineState:
        if state.weights is None:
            return state
        realised = float(state.context.get("portfolio_volatility", 0.0) or 0.0)
        if realised <= 0.0:
            return state
        scale = min(self.target_vol / realised, self.max_scale)
        state.weights = np.asarray(state.weights, dtype=np.float64) * float(scale)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "target_vol": self.target_vol,
            "max_scale": self.max_scale,
        }


__all__ = [
    "ConstantTimingAdjuster",
    "TimingAdjuster",
    "TurbulenceTimingAdjuster",
    "VolatilityTargetingTimingAdjuster",
]
