"""Agent decision providers for strategies.

Live and paper strategies can await `AgentRuntimeDecisionProvider.decide`.
Backtests should use `CachedAgentDecisionProvider` so replay remains
deterministic and inexpensive.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, Rating5, TraderAction, parse_rating
from aqp.core.registry import register

logger = logging.getLogger(__name__)


class BaseAgentDecisionProvider:
    """Common surface for strategy components that need agent decisions."""

    async def decide(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any] | None = None,
    ) -> AgentDecision | None:
        raise NotImplementedError

    def decide_sync(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any] | None = None,
    ) -> AgentDecision | None:
        return asyncio.run(self.decide(vt_symbol, timestamp, context))


@register("CachedAgentDecisionProvider")
class CachedAgentDecisionProvider(BaseAgentDecisionProvider):
    """Synchronous-friendly provider backed by `DecisionCache`."""

    def __init__(self, strategy_id: str = "default", cache_root: str | None = None) -> None:
        self.cache = DecisionCache(root=cache_root, strategy_id=strategy_id)

    async def decide(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any] | None = None,
    ) -> AgentDecision | None:
        return self.cache.get(vt_symbol, timestamp)

    def decide_sync(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any] | None = None,
    ) -> AgentDecision | None:
        return self.cache.get(vt_symbol, timestamp)


@register("AgentRuntimeDecisionProvider")
class AgentRuntimeDecisionProvider(BaseAgentDecisionProvider):
    """Async provider that runs a spec-driven agent via `AgentRuntime`."""

    def __init__(
        self,
        spec_name: str,
        prompt_template: str | None = None,
        cache_root: str | None = None,
        strategy_id: str = "default",
        write_cache: bool = True,
    ) -> None:
        self.spec_name = spec_name
        self.prompt_template = prompt_template or (
            "Return a JSON trading decision for {vt_symbol} at {timestamp}: "
            "action BUY/SELL/HOLD, size_pct, confidence, rating, rationale."
        )
        self.cache = DecisionCache(root=cache_root, strategy_id=strategy_id)
        self.write_cache = bool(write_cache)

    async def decide(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any] | None = None,
    ) -> AgentDecision | None:
        return await asyncio.to_thread(self._decide_blocking, vt_symbol, timestamp, context or {})

    def _decide_blocking(
        self,
        vt_symbol: str,
        timestamp: datetime,
        context: dict[str, Any],
    ) -> AgentDecision | None:
        from aqp.agents.runtime import runtime_for

        prompt = self.prompt_template.format(
            vt_symbol=vt_symbol,
            timestamp=timestamp,
            **context,
        )
        result = runtime_for(self.spec_name).run(
            {
                "prompt": prompt,
                "vt_symbol": vt_symbol,
                "timestamp": timestamp.isoformat(),
                **context,
            }
        )
        decision = _decision_from_payload(
            getattr(result, "output", result),
            vt_symbol=vt_symbol,
            timestamp=timestamp,
            provider=f"agent:{self.spec_name}",
        )
        if decision is not None and self.write_cache:
            self.cache.put(decision)
        return decision


def coerce_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    return pd.Timestamp(value).to_pydatetime()


def _decision_from_payload(
    payload: Any,
    *,
    vt_symbol: str,
    timestamp: datetime,
    provider: str,
) -> AgentDecision | None:
    if not isinstance(payload, dict):
        return None
    action_raw = str(payload.get("action") or payload.get("decision") or "HOLD").upper()
    if action_raw in {"BUY", "LONG"}:
        action = TraderAction.BUY
    elif action_raw in {"SELL", "SHORT"}:
        action = TraderAction.SELL
    else:
        action = TraderAction.HOLD
    rating_raw = payload.get("rating")
    rating = parse_rating(str(rating_raw)) if rating_raw is not None else Rating5.HOLD
    return AgentDecision(
        vt_symbol=vt_symbol,
        timestamp=timestamp,
        action=action,
        size_pct=float(payload.get("size_pct") or payload.get("strength") or 0.0),
        confidence=float(payload.get("confidence") or 0.5),
        rating=rating,
        rationale=str(payload.get("rationale") or payload.get("reason") or ""),
        evidence=list(payload.get("evidence") or []),
        provider=provider,
    )


__all__ = [
    "AgentRuntimeDecisionProvider",
    "BaseAgentDecisionProvider",
    "CachedAgentDecisionProvider",
    "coerce_timestamp",
]
