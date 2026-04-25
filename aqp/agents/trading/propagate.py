"""TradingAgents-style ``propagate`` entry point.

The single atomic call the rest of the platform uses to obtain one
:class:`AgentDecision` for a given ``(symbol, date)``. Mirrors the
TradingAgents ``propagate`` API from the TauricResearch project:

    decision = propagate("AAPL.NASDAQ", "2024-03-15")

Wraps :func:`aqp.agents.trading.crew.run_trader_crew` and takes care of:

- coercing the timestamp to a ``datetime``;
- resolving the crew config from a preset or dict;
- cache-through via :class:`aqp.agents.trading.decision_cache.DecisionCache`
  when one is supplied.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.agents.trading.crew import TraderCrewConfig, build_trader_crew_config, run_trader_crew
from aqp.agents.trading.types import AgentDecision

logger = logging.getLogger(__name__)


def _coerce_ts(ts: datetime | str) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return pd.to_datetime(ts).to_pydatetime()


def propagate(
    vt_symbol: str,
    as_of: datetime | str,
    config: TraderCrewConfig | dict[str, Any] | str | None = None,
    *,
    cache: Any | None = None,
    crew_run_id: str | None = None,
    force: bool = False,
) -> AgentDecision:
    """Run the trader crew for one ``(symbol, date)`` and return a decision.

    Args:
        vt_symbol: Canonical ``vt_symbol`` (``AAPL.NASDAQ``).
        as_of: Decision timestamp. Forward-looking bars must not be
            readable by the tools.
        config: Either a :class:`TraderCrewConfig`, a dict override, or
            the string name of a preset (defaults to
            ``settings.agentic_default_preset``).
        cache: Optional :class:`aqp.agents.trading.decision_cache.DecisionCache`.
            If supplied, a cache hit skips the LLM round trip.
        crew_run_id: Optional correlation id (used by the Celery task to
            thread DB rows together).
        force: Ignore cache and recompute.
    """
    ts = _coerce_ts(as_of)

    if isinstance(config, TraderCrewConfig):
        cfg = config
    elif isinstance(config, str):
        cfg = TraderCrewConfig.from_preset(config)
    elif isinstance(config, dict):
        cfg = build_trader_crew_config(
            preset=config.get("preset"),
            overrides={k: v for k, v in config.items() if k != "preset"},
        )
    else:
        cfg = build_trader_crew_config()

    if cache is not None and not force:
        cached = cache.get(vt_symbol, ts)
        if cached is not None:
            logger.debug(
                "decision-cache hit for %s @ %s (context_hash=%s)",
                vt_symbol,
                ts.isoformat(),
                getattr(cached, "context_hash", ""),
            )
            return cached

    decision = run_trader_crew(vt_symbol, ts, cfg, crew_run_id=crew_run_id)
    if cache is not None:
        cache.put(decision)
    return decision


__all__ = ["propagate", "TraderCrewConfig", "build_trader_crew_config"]
