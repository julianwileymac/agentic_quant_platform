"""Trailing-stop risk model (Lean ``TrailingStopRiskManagementModel``)."""
from __future__ import annotations

from typing import Any

from aqp.core.interfaces import IRiskManagementModel
from aqp.core.registry import register
from aqp.core.types import PortfolioTarget


@register("TrailingStopRisk")
class TrailingStopRisk(IRiskManagementModel):
    """Flatten a target whenever its trailing high-to-current drop exceeds ``trail_pct``.

    Expects ``context["peak_prices"]`` (``vt_symbol -> peak``) and
    ``context["prices"]`` (``vt_symbol -> last``). The `FrameworkAlgorithm`
    populates these via the broker's mark-to-market; paper sessions do
    the same through their history window.
    """

    def __init__(self, trail_pct: float = 0.05) -> None:
        self.trail_pct = float(trail_pct)

    def evaluate(self, targets: list[PortfolioTarget], context: dict[str, Any]) -> list[PortfolioTarget]:
        peaks = context.get("peak_prices") or {}
        prices = context.get("prices") or {}
        if not peaks or not prices:
            return targets
        stopped: set[str] = set()
        for vt_symbol, peak in peaks.items():
            last = prices.get(vt_symbol)
            if not (peak and last and peak > 0):
                continue
            if (peak - last) / peak >= self.trail_pct:
                stopped.add(vt_symbol)
        if not stopped:
            return targets
        return [t for t in targets if t.symbol.vt_symbol not in stopped]
