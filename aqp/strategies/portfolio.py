"""Portfolio-construction models (Lean stage 3)."""
from __future__ import annotations

from typing import Any

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import register
from aqp.core.types import Direction, PortfolioTarget, Signal


@register("EqualWeightPortfolio")
class EqualWeightPortfolio(IPortfolioConstructionModel):
    """Equal-weight the N strongest signals, capped at ``max_positions``."""

    def __init__(self, max_positions: int = 5, long_only: bool = True) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)

    def construct(
        self, signals: list[Signal], context: dict[str, Any]
    ) -> list[PortfolioTarget]:
        if not signals:
            return []
        ranked = sorted(
            signals, key=lambda s: s.strength * s.confidence, reverse=True
        )
        if self.long_only:
            ranked = [s for s in ranked if s.direction == Direction.LONG]
        ranked = ranked[: self.max_positions]
        if not ranked:
            return []
        weight = 1.0 / len(ranked)
        out: list[PortfolioTarget] = []
        for s in ranked:
            direction_sign = 1.0 if s.direction == Direction.LONG else -1.0
            out.append(
                PortfolioTarget(
                    symbol=s.symbol,
                    target_weight=direction_sign * weight,
                    rationale=s.rationale,
                    horizon_days=s.horizon_days,
                )
            )
        return out


@register("SignalWeightedPortfolio")
class SignalWeightedPortfolio(IPortfolioConstructionModel):
    """Weights proportional to signal strength × confidence, normalised to ±1."""

    def __init__(self, max_positions: int = 10, long_only: bool = False) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)

    def construct(
        self, signals: list[Signal], context: dict[str, Any]
    ) -> list[PortfolioTarget]:
        if not signals:
            return []
        candidates = sorted(
            signals, key=lambda s: s.strength * s.confidence, reverse=True
        )
        if self.long_only:
            candidates = [s for s in candidates if s.direction == Direction.LONG]
        candidates = candidates[: self.max_positions]
        if not candidates:
            return []
        total = sum(s.strength * s.confidence for s in candidates) or 1.0
        out: list[PortfolioTarget] = []
        for s in candidates:
            sign = 1.0 if s.direction == Direction.LONG else -1.0
            w = sign * (s.strength * s.confidence) / total
            out.append(
                PortfolioTarget(
                    symbol=s.symbol,
                    target_weight=w,
                    rationale=s.rationale,
                    horizon_days=s.horizon_days,
                )
            )
        return out
