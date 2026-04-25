"""Sector exposure risk model (Lean ``MaximumSectorExposureRiskManagementModel``)."""
from __future__ import annotations

from typing import Any

from aqp.core.interfaces import IRiskManagementModel
from aqp.core.registry import register
from aqp.core.types import PortfolioTarget


@register("MaxSectorExposure")
class MaxSectorExposure(IRiskManagementModel):
    """Cap gross exposure within any single sector.

    The ``sector_map`` is a ``vt_symbol -> sector`` dictionary either
    passed in at construction or placed in ``context["sector_map"]`` by
    the strategy's universe model.
    """

    def __init__(self, max_sector_pct: float = 0.35, sector_map: dict[str, str] | None = None) -> None:
        self.max_sector_pct = float(max_sector_pct)
        self.sector_map = dict(sector_map or {})

    def evaluate(self, targets: list[PortfolioTarget], context: dict[str, Any]) -> list[PortfolioTarget]:
        mapping = {**(context.get("sector_map") or {}), **self.sector_map}
        if not mapping or not targets:
            return targets
        per_sector: dict[str, float] = {}
        for t in targets:
            sector = mapping.get(t.symbol.vt_symbol, "UNKNOWN")
            per_sector[sector] = per_sector.get(sector, 0.0) + abs(t.target_weight)
        # Scale down per-sector if any sector breaches the cap.
        scale_by_sector: dict[str, float] = {}
        for sector, exposure in per_sector.items():
            if exposure > self.max_sector_pct:
                scale_by_sector[sector] = self.max_sector_pct / exposure
        if not scale_by_sector:
            return targets
        scaled: list[PortfolioTarget] = []
        for t in targets:
            sector = mapping.get(t.symbol.vt_symbol, "UNKNOWN")
            scale = scale_by_sector.get(sector, 1.0)
            if scale >= 1.0:
                scaled.append(t)
                continue
            new_weight = t.target_weight * scale
            if abs(new_weight) < 1e-4:
                continue
            scaled.append(
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=float(new_weight),
                    rationale=f"{t.rationale or ''} [sector-cap×{scale:.2f}]".strip(),
                    horizon_days=t.horizon_days,
                )
            )
        return scaled
