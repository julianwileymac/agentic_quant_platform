"""IAlphaModel adapter for the FinGPT-Forecaster."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol
from aqp.ml.applications.forecaster.forecaster import FinGPTForecaster

logger = logging.getLogger(__name__)


@register("ForecasterAlpha")
class ForecasterAlpha(IAlphaModel):
    """Wrap :class:`FinGPTForecaster` as a plain alpha.

    Emits one signal per symbol per call; expensive, so use a weekly or
    monthly rebalance in your backtest config. Cache the forecaster
    output via :class:`aqp.agents.trading.decision_cache.DecisionCache`
    if you need per-bar replay.
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        n_past_weeks: int = 2,
        min_confidence: float = 0.5,
        strength: float = 0.15,
    ) -> None:
        self.forecaster = FinGPTForecaster(
            provider=provider,
            model=model,
            n_past_weeks=n_past_weeks,
        )
        self.min_confidence = float(min_confidence)
        self.strength = float(strength)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        ts: datetime = context.get("current_time") or datetime.utcnow()
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()

        signals: list[Signal] = []
        for sym in universe:
            try:
                out = self.forecaster.forecast(sym.ticker, ts)
            except Exception as exc:  # pragma: no cover - runtime
                logger.warning("forecaster call failed for %s: %s", sym.ticker, exc)
                continue
            if out.confidence < self.min_confidence or out.direction_num == 0:
                continue
            signals.append(
                Signal(
                    symbol=sym,
                    strength=self.strength * abs(out.direction_num),
                    direction=Direction.LONG if out.direction_num > 0 else Direction.SHORT,
                    timestamp=ts,
                    confidence=out.confidence,
                    horizon_days=out.horizon_days,
                    source=f"FinGPT-Forecaster({out.model})",
                    rationale=out.rationale or None,
                )
            )
        return signals
