"""Composable signal components for vectorized backtests."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import build_from_config, register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


@register("AlphaSignalComponent")
class AlphaSignalComponent(IAlphaModel):
    """Thin wrapper that makes an existing alpha usable as a named component."""

    def __init__(self, alpha: IAlphaModel | dict[str, Any]) -> None:
        self.alpha = build_from_config(alpha) if isinstance(alpha, dict) else alpha

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        return list(self.alpha.generate_signals(bars, universe, context))


@register("CompositeAlpha")
class CompositeAlpha(IAlphaModel):
    """Fan out to multiple alpha components and concatenate their signals."""

    def __init__(self, components: list[IAlphaModel | dict[str, Any]]) -> None:
        self.components = [
            build_from_config(component) if isinstance(component, dict) else component
            for component in components
        ]

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        signals: list[Signal] = []
        for component in self.components:
            try:
                signals.extend(component.generate_signals(bars, universe, context))
            except Exception:
                logger.exception("%s failed during signal generation", type(component).__name__)
        return signals


@register("AgentRuntimeAlpha")
class AgentRuntimeAlpha(IAlphaModel):
    """Call a spec-driven agent and convert its action output into signals.

    This is the live/audit bridge for vectorized research. Deterministic
    backtests should prefer `AgenticAlpha` in precompute mode.
    """

    def __init__(
        self,
        spec_name: str,
        prompt_template: str | None = None,
        max_symbols: int | None = 20,
        default_strength: float = 0.1,
        min_confidence: float = 0.0,
    ) -> None:
        self.spec_name = spec_name
        self.prompt_template = prompt_template or (
            "Produce a trading action for {vt_symbol} at {timestamp}. "
            "Return JSON with action, confidence, size_pct, and rationale."
        )
        self.max_symbols = int(max_symbols) if max_symbols else None
        self.default_strength = float(default_strength)
        self.min_confidence = float(min_confidence)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        from aqp.agents.runtime import runtime_for

        runtime = runtime_for(self.spec_name)
        ts = context.get("current_time") or context.get("timestamp")
        selected = universe[: self.max_symbols] if self.max_symbols else universe
        signals: list[Signal] = []
        for symbol in selected:
            latest = _latest_bar_payload(bars, symbol.vt_symbol)
            prompt = self.prompt_template.format(
                vt_symbol=symbol.vt_symbol,
                timestamp=ts,
                latest_bar=latest,
            )
            try:
                result = runtime.run(
                    {
                        "prompt": prompt,
                        "vt_symbol": symbol.vt_symbol,
                        "timestamp": str(ts),
                        "latest_bar": latest,
                    }
                )
            except Exception:
                logger.exception("agent runtime failed for %s", symbol.vt_symbol)
                continue
            signal = _payload_to_signal(
                getattr(result, "output", result),
                symbol=symbol,
                timestamp=ts,
                default_strength=self.default_strength,
                min_confidence=self.min_confidence,
                source=f"agent:{self.spec_name}",
            )
            if signal is not None:
                signals.append(signal)
        return signals


@register("ModelPredictionAlpha")
class ModelPredictionAlpha(IAlphaModel):
    """Use a model's latest per-symbol prediction as an alpha signal."""

    def __init__(
        self,
        model: Any | dict[str, Any],
        feature_columns: list[str],
        long_threshold: float = 0.0,
        short_threshold: float = 0.0,
        allow_short: bool = True,
        strength_scale: float = 1.0,
    ) -> None:
        self.model = build_from_config(model) if isinstance(model, dict) else model
        self.feature_columns = list(feature_columns)
        self.long_threshold = float(long_threshold)
        self.short_threshold = float(short_threshold)
        self.allow_short = bool(allow_short)
        self.strength_scale = float(strength_scale)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty or not self.feature_columns:
            return []
        latest = bars.sort_values("timestamp").groupby("vt_symbol", as_index=False).tail(1)
        universe_by_vt = {symbol.vt_symbol: symbol for symbol in universe}
        latest = latest[latest["vt_symbol"].isin(universe_by_vt)]
        if latest.empty:
            return []
        missing = [col for col in self.feature_columns if col not in latest.columns]
        if missing:
            logger.warning("missing model feature columns: %s", missing)
            return []
        x = latest[self.feature_columns].fillna(0.0).to_numpy()
        preds = np.asarray(self.model.predict(x), dtype=float).reshape(-1)
        signals: list[Signal] = []
        ts = context.get("current_time") or context.get("timestamp")
        for row, pred in zip(latest.to_dict(orient="records"), preds, strict=False):
            symbol = universe_by_vt[str(row["vt_symbol"])]
            if pred > self.long_threshold:
                direction = Direction.LONG
            elif self.allow_short and pred < self.short_threshold:
                direction = Direction.SHORT
            else:
                continue
            signals.append(
                Signal(
                    symbol=symbol,
                    strength=min(1.0, abs(float(pred)) * self.strength_scale),
                    direction=direction,
                    timestamp=ts,
                    confidence=min(1.0, abs(float(pred))),
                    source="ml:model_prediction",
                )
            )
        return signals


def _latest_bar_payload(bars: pd.DataFrame, vt_symbol: str) -> dict[str, Any]:
    if bars is None or bars.empty:
        return {}
    sub = bars[bars["vt_symbol"] == vt_symbol].sort_values("timestamp")
    if sub.empty:
        return {}
    row = sub.iloc[-1].to_dict()
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in row.items()}


def _payload_to_signal(
    payload: Any,
    *,
    symbol: Symbol,
    timestamp: Any,
    default_strength: float,
    min_confidence: float,
    source: str,
) -> Signal | None:
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or payload.get("direction") or payload.get("decision") or "").lower()
    confidence = float(payload.get("confidence") or 0.5)
    if confidence < min_confidence:
        return None
    if action in {"buy", "long"}:
        direction = Direction.LONG
    elif action in {"sell", "short"}:
        direction = Direction.SHORT
    else:
        return None
    strength = float(payload.get("size_pct") or payload.get("strength") or default_strength)
    return Signal(
        symbol=symbol,
        strength=max(0.0, min(1.0, strength)),
        direction=direction,
        timestamp=timestamp,
        confidence=confidence,
        source=source,
        rationale=payload.get("rationale") or payload.get("reason"),
    )


__all__ = [
    "AgentRuntimeAlpha",
    "AlphaSignalComponent",
    "CompositeAlpha",
    "ModelPredictionAlpha",
]
