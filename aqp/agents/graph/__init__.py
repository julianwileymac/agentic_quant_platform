"""LangGraph orchestration for spec-driven agent teams.

Inspired by TradingAgents' ``StateGraph`` (analysts → researchers →
trader → risk → PM) but rebuilt around AQP's :class:`AgentSpec` +
:class:`AgentRuntime` so the graph is composable from any registered
spec and the per-step state is persisted alongside the spec version
that produced it.

Public API
----------

- :func:`build_research_graph` — research → equity → universe.
- :func:`build_trader_graph` — trader → analysis run.
- :func:`build_full_pipeline_graph` — research → selection → trader →
  analysis (the canonical end-to-end agentic loop, paper Sections 2 / 3).
- :func:`build_research_debate_graph` — Phase 4 multi-agent consensus:
  Market Monitor → Quant Generator → Risk Simulator → emit/reject gate.
- :class:`AgentState` — TypedDict carried between nodes.
- :class:`RedisCheckpointer` — Redis-backed LangGraph checkpointer.
- :func:`append_pending_decision` / :func:`resolve_pending_decisions` —
  TradingAgents-style decision log.

When LangGraph isn't installed, the builders return a deterministic
:class:`SequentialGraph` fallback that runs nodes in order and skips
conditional routing — so unit tests + cold-install dev loops still
exercise the wiring.
"""
from __future__ import annotations

from aqp.agents.graph.builder import (
    SequentialGraph,
    build_full_pipeline_graph,
    build_research_debate_graph,
    build_research_graph,
    build_trader_graph,
)
from aqp.agents.graph.checkpointer import RedisCheckpointer
from aqp.agents.graph.conditions import (
    risk_simulator_approves,
    should_consult_rag,
    should_continue_debate,
    should_continue_risk,
)
from aqp.agents.graph.decision_log import (
    append_pending_decision,
    resolve_pending_decisions,
)
from aqp.agents.graph.state import AgentState, RiskDebateState, ResearchDebateState

__all__ = [
    "AgentState",
    "RedisCheckpointer",
    "ResearchDebateState",
    "RiskDebateState",
    "SequentialGraph",
    "append_pending_decision",
    "build_full_pipeline_graph",
    "build_research_debate_graph",
    "build_research_graph",
    "build_trader_graph",
    "resolve_pending_decisions",
    "risk_simulator_approves",
    "should_consult_rag",
    "should_continue_debate",
    "should_continue_risk",
]
