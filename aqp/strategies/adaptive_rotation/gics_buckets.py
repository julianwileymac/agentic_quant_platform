"""GICS sector → high-level bucket map for rotation strategies.

Mirrors :mod:`group_selection_by_gics` from the FinRL-Trading
inspiration repo. Buckets:

- ``growth_tech`` — high-growth, high-multiple
- ``cyclical`` — economically sensitive
- ``real_assets`` — energy, materials, real estate
- ``defensive`` — staples, utilities, healthcare
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.core.interfaces import IUniverseSelectionModel
from aqp.core.registry import register
from aqp.core.types import Symbol

logger = logging.getLogger(__name__)


SECTOR_TO_BUCKET: dict[str, str] = {
    # Growth tech
    "information technology": "growth_tech",
    "technology": "growth_tech",
    "communication services": "growth_tech",
    "communication": "growth_tech",
    # Cyclical
    "consumer discretionary": "cyclical",
    "consumer cyclical": "cyclical",
    "industrials": "cyclical",
    "financials": "cyclical",
    "financial services": "cyclical",
    # Real assets
    "energy": "real_assets",
    "materials": "real_assets",
    "basic materials": "real_assets",
    "real estate": "real_assets",
    # Defensive
    "consumer staples": "defensive",
    "utilities": "defensive",
    "health care": "defensive",
    "healthcare": "defensive",
}


BUCKET_TO_DEFAULT_WEIGHT: dict[str, dict[str, float]] = {
    "risk_on": {
        "growth_tech": 0.45,
        "cyclical": 0.30,
        "real_assets": 0.15,
        "defensive": 0.10,
    },
    "neutral": {
        "growth_tech": 0.30,
        "cyclical": 0.25,
        "real_assets": 0.20,
        "defensive": 0.25,
    },
    "risk_off": {
        "growth_tech": 0.15,
        "cyclical": 0.15,
        "real_assets": 0.20,
        "defensive": 0.50,
    },
}


def _sector_to_bucket(sector: str | None) -> str | None:
    if not sector:
        return None
    return SECTOR_TO_BUCKET.get(sector.strip().lower())


@register(
    "GICSBucketUniverseSelector",
    kind="universe",
    tags=("universe", "rotation", "gics"),
)
class GICSBucketUniverseSelector(IUniverseSelectionModel):
    """Group every base universe member into GICS buckets and emit a flat list.

    Resolves sectors from :class:`aqp.persistence.models.Instrument` (or
    :class:`aqp.persistence.models_entities.Issuer.industry_classifications`
    when available). Symbols whose sector cannot be resolved go into the
    ``unknown`` bucket and are dropped unless ``keep_unknown=True``.
    """

    def __init__(
        self,
        base_universe: list[str] | None = None,
        per_bucket_target: int = 5,
        keep_unknown: bool = False,
        active_buckets: list[str] | None = None,
    ) -> None:
        self.base_universe = list(base_universe or [])
        self.per_bucket_target = max(1, int(per_bucket_target))
        self.keep_unknown = bool(keep_unknown)
        self.active_buckets = (
            [b.lower() for b in active_buckets] if active_buckets else None
        )

    def _bucket_map(self, vt_symbols: list[str]) -> dict[str, str]:
        if not vt_symbols:
            return {}
        try:
            from sqlalchemy import select

            from aqp.persistence.db import get_session
            from aqp.persistence.models import Instrument

            with get_session() as session:
                rows = session.execute(
                    select(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
                ).scalars().all()
        except Exception:
            logger.info("GICS selector: instrument lookup failed", exc_info=True)
            return {}
        out: dict[str, str] = {}
        for r in rows:
            bucket = _sector_to_bucket(getattr(r, "sector", None))
            if bucket is not None:
                out[r.vt_symbol] = bucket
            elif self.keep_unknown:
                out[r.vt_symbol] = "unknown"
        return out

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        base = list(self.base_universe or context.get("base_universe") or [])
        if not base:
            return []
        bucket_map = self._bucket_map(base)
        # If active_buckets is configured, only keep those.
        kept_per_bucket: dict[str, list[str]] = {}
        for sym, bucket in bucket_map.items():
            if self.active_buckets and bucket not in self.active_buckets:
                continue
            kept_per_bucket.setdefault(bucket, []).append(sym)
        out: list[Symbol] = []
        for bucket, syms in kept_per_bucket.items():
            for sym in syms[: self.per_bucket_target]:
                try:
                    out.append(Symbol.parse(sym))
                except Exception:
                    continue
        # Stash the bucket map in context so downstream alphas can read it.
        context.setdefault("_gics_bucket_map", bucket_map)
        return out


__all__ = [
    "BUCKET_TO_DEFAULT_WEIGHT",
    "GICSBucketUniverseSelector",
    "SECTOR_TO_BUCKET",
]
