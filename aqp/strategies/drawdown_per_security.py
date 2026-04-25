"""Per-security drawdown stop (Lean ``MaximumDrawdownPercentPerSecurity``)."""
from __future__ import annotations

from typing import Any

from aqp.core.interfaces import IRiskManagementModel
from aqp.core.registry import register
from aqp.core.types import PortfolioTarget


@register("MaxDrawdownPerSecurity")
class MaxDrawdownPerSecurity(IRiskManagementModel):
    """Kill a symbol's target whenever its position has drawn down past ``max_pct``."""

    def __init__(self, max_pct: float = 0.15) -> None:
        self.max_pct = float(max_pct)

    def evaluate(self, targets: list[PortfolioTarget], context: dict[str, Any]) -> list[PortfolioTarget]:
        positions = context.get("positions") or []
        # ``positions`` may be a list or dict; tolerate both.
        if isinstance(positions, dict):
            positions = list(positions.values())
        drawn_down: set[str] = set()
        for pos in positions:
            sym = getattr(pos, "symbol", None)
            if sym is None:
                continue
            peak = context.get("peak_prices", {}).get(sym.vt_symbol)
            current = context.get("prices", {}).get(sym.vt_symbol)
            if peak and current and peak > 0:
                dd = (peak - current) / peak
                if dd >= self.max_pct:
                    drawn_down.add(sym.vt_symbol)
        if not drawn_down:
            return targets
        return [t for t in targets if t.symbol.vt_symbol not in drawn_down]
