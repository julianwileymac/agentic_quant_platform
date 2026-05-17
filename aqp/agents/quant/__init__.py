"""Quant-research agents — Alpha Researcher + Strategy Executor (Phase 4).

These are the two agent identities in the FinRL-X blueprint. Both
are driven by :class:`aqp.agents.runtime.AgentRuntime` (rule 12) and
use ``router_complete`` for every LLM call (rule 2). They read AQP
state exclusively through DataMCPTools (rule 22) and write back via
documented MCP tools or HTTP endpoints.

- :class:`AlphaResearcher` wraps the symbolic-DSL evaluation +
  ``FactorNode`` compilation so a Celery task can drive
  AgentRuntime → reward computation → spec mutation cycle without
  the runtime needing to know about the AST sandbox internals.
- :class:`StrategyExecutor` wraps the dispatch helpers around
  :class:`aqp.rl.runtime.RLRuntime` so the agent's JSON action
  output translates into the appropriate runtime call (train,
  evaluate, paper, replay).
"""
from __future__ import annotations

from aqp.agents.quant.alpha_researcher import (
    AlphaResearcher,
    AlphaResearcherResult,
)
from aqp.agents.quant.strategy_executor import (
    StrategyExecutor,
    StrategyExecutorResult,
)

__all__ = [
    "AlphaResearcher",
    "AlphaResearcherResult",
    "StrategyExecutor",
    "StrategyExecutorResult",
]
