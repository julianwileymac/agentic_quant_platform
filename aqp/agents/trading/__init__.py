"""Trading-specific agent crew, domain types, cache, and propagate harness.

This package is the TradingAgents-inspired counterpart of the generic
research crew in :mod:`aqp.agents`. While the research crew produces
**strategy YAML** that the platform later backtests, this package
produces **per-bar ``AgentDecision`` objects** that feed the
``AgenticAlpha`` during a backtest.

Sub-modules:

- :mod:`aqp.agents.trading.types` — canonical Pydantic/dataclass domain
  types (``Rating5``, ``AnalystReport``, ``DebateTurn``, ``TraderPlan``,
  ``RiskVerdict``, ``AgentDecision``).
- :mod:`aqp.agents.trading.prompts` — role-specific system prompts.
- :mod:`aqp.agents.trading.roles` — role execution primitives (direct
  LLM calls + optional CrewAI agent factories).
- :mod:`aqp.agents.trading.crew` — ``run_trader_crew`` that wires the
  analysts → debate → trader → risk → PM pipeline.
- :mod:`aqp.agents.trading.propagate` — ``propagate(symbol, date, cfg)``
  atom that produces one ``AgentDecision``.
- :mod:`aqp.agents.trading.decision_cache` — Parquet + DuckDB cache.
"""
from __future__ import annotations

from aqp.agents.trading.crew import (
    TraderCrewConfig,
    build_trader_crew_config,
    run_trader_crew,
)
from aqp.agents.trading.decision_cache import DecisionCache, get_default_cache
from aqp.agents.trading.propagate import propagate
from aqp.agents.trading.types import (
    AgentDecision,
    AnalystReport,
    DebateTurn,
    PortfolioDecision,
    Rating5,
    RiskVerdict,
    TraderAction,
    TraderPlan,
    parse_rating,
)

__all__ = [
    "AgentDecision",
    "AnalystReport",
    "DebateTurn",
    "DecisionCache",
    "PortfolioDecision",
    "Rating5",
    "RiskVerdict",
    "TraderAction",
    "TraderCrewConfig",
    "TraderPlan",
    "build_trader_crew_config",
    "get_default_cache",
    "parse_rating",
    "propagate",
    "run_trader_crew",
]
