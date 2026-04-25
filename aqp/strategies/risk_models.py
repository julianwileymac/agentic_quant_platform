"""Risk-management models (Lean stage 4)."""
from __future__ import annotations

from typing import Any

from aqp.core.interfaces import IRiskManagementModel
from aqp.core.registry import register
from aqp.core.types import PortfolioTarget


@register("BasicRiskModel")
class BasicRiskModel(IRiskManagementModel):
    """Cap each position weight and bail on drawdown breaches."""

    def __init__(
        self,
        max_position_pct: float = 0.20,
        max_drawdown_pct: float = 0.15,
        leverage: float = 1.0,
    ) -> None:
        self.max_position_pct = float(max_position_pct)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.leverage = float(leverage)

    def evaluate(
        self, targets: list[PortfolioTarget], context: dict[str, Any]
    ) -> list[PortfolioTarget]:
        drawdown = float(context.get("drawdown", 0.0))
        if drawdown <= -self.max_drawdown_pct:
            return []

        cap = self.max_position_pct
        lev = self.leverage
        out: list[PortfolioTarget] = []
        for t in targets:
            clipped = max(-cap, min(cap, t.target_weight * lev))
            if abs(clipped) < 1e-4:
                continue
            out.append(
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=clipped,
                    rationale=t.rationale,
                    horizon_days=t.horizon_days,
                )
            )
        total = sum(abs(t.target_weight) for t in out)
        if total > 1.0:
            scale = 1.0 / total
            out = [
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=t.target_weight * scale,
                    rationale=t.rationale,
                    horizon_days=t.horizon_days,
                )
                for t in out
            ]
        return out


@register("NoOpRiskModel")
class NoOpRiskModel(IRiskManagementModel):
    """Pass-through — convenient for debugging."""

    def evaluate(self, targets, context):
        return list(targets)
