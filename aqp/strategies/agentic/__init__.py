"""Agentic alphas — strategies whose signals come from LLM trader decisions.

Houses:

- :class:`aqp.strategies.agentic.agentic_alpha.AgenticAlpha` — reads a
  :class:`aqp.agents.trading.decision_cache.DecisionCache` and emits
  :class:`aqp.core.types.Signal` objects per bar.
- :class:`aqp.strategies.agentic.agent_aware_alpha.AgentAwareMomentumAlpha`
  — worked example of an alpha that consults an agent on every bar via
  the :class:`AgentDispatcher` exposed at ``context['agents']`` by the
  event-driven engine.
- :class:`aqp.strategies.agentic.agent_dispatcher.AgentDispatcher` — the
  primitive used by such strategies. TTL + LRU cached sync wrapper around
  :class:`aqp.agents.runtime.AgentRuntime.run`.
- :class:`aqp.strategies.agentic.ml_selector_alpha.MLSelectorAlpha` —
  FinRL-Trading style Random Forest stock selector.
"""
from __future__ import annotations

from aqp.strategies.agentic.agent_aware_alpha import AgentAwareMomentumAlpha
from aqp.strategies.agentic.agent_dispatcher import (
    AgentDispatcher,
    get_default_dispatcher,
)
from aqp.strategies.agentic.agentic_alpha import AgenticAlpha, AgenticAlphaMode
from aqp.strategies.agentic.decision_provider import (
    AgentRuntimeDecisionProvider,
    BaseAgentDecisionProvider,
    CachedAgentDecisionProvider,
)
from aqp.strategies.agentic.ml_selector_alpha import MLSelectorAlpha

__all__ = [
    "AgentAwareMomentumAlpha",
    "AgentDispatcher",
    "AgentRuntimeDecisionProvider",
    "AgenticAlpha",
    "AgenticAlphaMode",
    "BaseAgentDecisionProvider",
    "CachedAgentDecisionProvider",
    "MLSelectorAlpha",
    "get_default_dispatcher",
]
