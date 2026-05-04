"""Configured fallback/cascade backtest engine."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.backtest.base import BaseBacktestEngine
from aqp.backtest.capabilities import EngineCapabilities
from aqp.backtest.engine import BacktestResult
from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import build_from_config, register

logger = logging.getLogger(__name__)


# Default fallback chain after the configured primary engine. The order is
# chosen so the fastest, richest engine ships first and progressively more
# permissive / niche options trail. ``primary="vectorbt-pro"`` plus this
# chain mirrors the rehauled stack: vbt-pro → event-driven (per-bar Python
# for true async agent dispatch) → AAT (async LOB fallback) → ZVT (CN bars
# fallback) → OSS vectorbt (last-ditch vectorised path).
DEFAULT_FALLBACK_CHAIN: tuple[str, ...] = (
    "event",
    "aat",
    "zvt",
    "vectorbt",
)


@register("FallbackBacktestEngine")
class FallbackBacktestEngine(BaseBacktestEngine):
    """Try a primary engine, then configured fallbacks on failure.

    This engine is opt-in and exists for research workflows where optional
    engines such as vectorbt Pro may not be installed on every machine.

    The default chain favours vbt-pro first (fastest), then the event-driven
    engine (richest semantics + per-bar agent dispatch), then AAT (async LOB),
    then ZVT (CN bars) — see :data:`DEFAULT_FALLBACK_CHAIN`.
    """

    capabilities = EngineCapabilities(
        name="fallback",
        description="Cascade — tries primary then fallback engines on failure.",
        supports_signals=True,
        supports_orders=True,
        supports_callbacks=True,
        supports_multi_asset=True,
        supports_short_selling=True,
        supports_leverage=True,
        supports_stops=True,
        supports_event_driven=True,
        supports_vectorized=True,
        supports_walk_forward=True,
        license="meta",
        notes="Capabilities depend on which engine is selected at runtime.",
    )

    def __init__(
        self,
        primary: str | dict[str, Any] = "vectorbt-pro",
        fallbacks: list[str | dict[str, Any]] | None = None,
    ) -> None:
        self.primary = primary
        self.fallbacks = list(fallbacks or list(DEFAULT_FALLBACK_CHAIN))

    def run(self, strategy: IAlphaModel | IStrategy, bars: pd.DataFrame) -> BacktestResult:
        errors: list[str] = []
        for spec in [self.primary, *self.fallbacks]:
            label = _label(spec)
            try:
                engine = _build_engine(spec)
                result = engine.run(strategy, bars)
                result.summary["engine"] = result.summary.get("engine") or label
                result.summary["selected_engine"] = result.summary["engine"]
                if errors:
                    result.summary["fallback_errors"] = errors
                return result
            except Exception as exc:
                logger.warning("Backtest engine %s failed: %s", label, exc)
                errors.append(f"{label}: {exc}")
        raise RuntimeError("All configured backtest engines failed: " + " | ".join(errors))


def _label(spec: str | dict[str, Any]) -> str:
    if isinstance(spec, str):
        return spec
    if "engine" in spec:
        return str(spec["engine"])
    return str(spec.get("class", "engine"))


def _build_engine(spec: str | dict[str, Any]):
    from aqp.backtest.runner import _resolve_backtest_cfg, build_engine

    if isinstance(spec, str):
        return build_engine(spec)
    if "engine" in spec and "class" not in spec:
        cfg, _ = _resolve_backtest_cfg(spec)
        return build_from_config(cfg)
    return build_from_config(spec)


__all__ = ["FallbackBacktestEngine", "DEFAULT_FALLBACK_CHAIN"]
