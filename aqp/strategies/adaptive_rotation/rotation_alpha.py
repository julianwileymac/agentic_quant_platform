"""Adaptive rotation alpha — bucket weight × intra-bucket TS-momentum rank."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol
from aqp.strategies.adaptive_rotation.gics_buckets import (
    BUCKET_TO_DEFAULT_WEIGHT,
    SECTOR_TO_BUCKET,
)
from aqp.strategies.adaptive_rotation.market_regime import MarketRegimeClassifier, Regime

logger = logging.getLogger(__name__)


def _ts_momentum(prices: pd.Series, lookback: int) -> float:
    """Time-series momentum signal (sign of (price - rolling-mean) / std)."""
    series = pd.to_numeric(prices, errors="coerce").dropna()
    if len(series) < lookback + 1:
        return 0.0
    tail = series.tail(lookback + 1)
    rets = tail.pct_change().dropna()
    if rets.empty or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std())


@register(
    "AdaptiveRotationAlpha",
    kind="strategy",
    tags=("rotation", "regime", "tsmom"),
    source="finrl_trading",
    category="rotation",
)
class AdaptiveRotationAlpha(IAlphaModel):
    """Rotate capital across GICS buckets according to market regime."""

    def __init__(
        self,
        benchmark_vt_symbol: str = "SPY.NYSE",
        regime_classifier: dict[str, Any] | None = None,
        bucket_weights: dict[str, dict[str, float]] | None = None,
        per_bucket_top_k: int = 3,
        momentum_lookback: int = 60,
        long_only: bool = True,
    ) -> None:
        self.benchmark_vt_symbol = str(benchmark_vt_symbol)
        self.regime_classifier = MarketRegimeClassifier(**(regime_classifier or {}))
        self.bucket_weights = bucket_weights or BUCKET_TO_DEFAULT_WEIGHT
        self.per_bucket_top_k = int(per_bucket_top_k)
        self.momentum_lookback = int(momentum_lookback)
        self.long_only = bool(long_only)

    def _bucket_map(self, vt_symbols: list[str]) -> dict[str, str]:
        try:
            from sqlalchemy import select

            from aqp.persistence.db import get_session
            from aqp.persistence.models import Instrument

            with get_session() as session:
                rows = session.execute(
                    select(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
                ).scalars().all()
            out: dict[str, str] = {}
            for r in rows:
                sector = (getattr(r, "sector", "") or "").lower()
                bucket = SECTOR_TO_BUCKET.get(sector)
                if bucket is not None:
                    out[r.vt_symbol] = bucket
            return out
        except Exception:
            logger.info("AdaptiveRotation: instrument lookup failed", exc_info=True)
            return {}

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty or not universe:
            return []
        regime: Regime = self.regime_classifier.classify_from_bars(
            bars, self.benchmark_vt_symbol
        )
        weights_by_bucket = self.bucket_weights.get(regime, BUCKET_TO_DEFAULT_WEIGHT["neutral"])
        vt_list = [s.vt_symbol for s in universe]
        bucket_map = context.get("_gics_bucket_map") or self._bucket_map(vt_list)
        if not bucket_map:
            return []

        # Compute momentum for every symbol.
        momentum: dict[str, float] = {}
        for sym in vt_list:
            sub = bars[bars["vt_symbol"] == sym].sort_values("timestamp")
            if sub.empty:
                continue
            momentum[sym] = _ts_momentum(sub["close"], self.momentum_lookback)

        # Group by bucket, take top-k by momentum, allocate weight per
        # bucket then equally among the kept members.
        per_bucket: dict[str, list[tuple[str, float]]] = {}
        for sym, bucket in bucket_map.items():
            if sym not in momentum:
                continue
            per_bucket.setdefault(bucket, []).append((sym, momentum[sym]))

        ts = context.get("current_time")
        if ts is None and not bars.empty:
            ts = pd.to_datetime(bars["timestamp"]).max()
        out: list[Signal] = []
        for bucket, members in per_bucket.items():
            bucket_weight = float(weights_by_bucket.get(bucket, 0.0))
            if bucket_weight <= 0:
                continue
            kept = sorted(members, key=lambda x: x[1], reverse=True)[
                : self.per_bucket_top_k
            ]
            if not kept:
                continue
            inner = bucket_weight / len(kept)
            for sym, score in kept:
                if score <= 0 and self.long_only:
                    continue
                direction = Direction.LONG if score >= 0 else Direction.SHORT
                if self.long_only and direction == Direction.SHORT:
                    continue
                out.append(
                    Signal(
                        symbol=Symbol.parse(sym),
                        strength=float(min(1.0, max(0.0, inner))),
                        direction=direction,
                        timestamp=ts,
                        confidence=float(min(1.0, abs(score))),
                        horizon_days=self.momentum_lookback,
                        source=type(self).__name__,
                        rationale=(
                            f"regime={regime} bucket={bucket} weight={inner:.3f} "
                            f"tsmom={score:.3f}"
                        ),
                    )
                )
        return out


__all__ = ["AdaptiveRotationAlpha"]
