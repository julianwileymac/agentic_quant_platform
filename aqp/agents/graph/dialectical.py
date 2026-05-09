"""Dialectical Bull/Bear/PortfolioManager debate graph.

Implements the TradingAgents-style adversarial reasoning pattern
described in the report: rather than a single agent producing a
verdict, the graph runs a Bull researcher and a Bear researcher in
parallel against the same simulation evidence, then routes their
debate transcripts to a Portfolio Manager who synthesises the final
verdict.

This complements the existing
:func:`aqp.agents.graph.builder.build_research_debate_graph` (monitor
→ generator → simulator) by sitting *after* simulation: the bull /
bear nodes consume the same ``simulation_verdict`` that
``risk_simulator`` produces, and the portfolio manager produces a
new ``debate_verdict`` slot. The Phase-4 iterative optimisation loop
keys on ``debate_verdict.action`` (``buy`` / ``hold`` / ``sell`` /
``mutate_params``) to decide whether to ship the signal or trigger
another iteration.

Three new agent specs ship under :file:`configs/agents/`:

- ``research.bull_researcher`` — argues for the proposed alpha.
- ``research.bear_researcher`` — argues against, surfacing risks.
- ``research.portfolio_manager`` — synthesises both into a verdict.

When LangGraph is installed each builder returns a compiled
``StateGraph``; without it the :class:`SequentialGraph` fallback runs
nodes in order (bull and bear are run sequentially in fallback mode,
so the audit trail stays identical).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.agents.graph.builder import (
    NodeFn,
    SequentialGraph,
    _agent_node,
)
from aqp.agents.graph.checkpointer import RedisCheckpointer
from aqp.agents.graph.state import AgentState

logger = logging.getLogger(__name__)


def _portfolio_manager_node(state: AgentState) -> AgentState:
    """Synthesise bull + bear arguments into a final verdict.

    The default behaviour (when no LLM-driven manager spec runs)
    averages the bull / bear confidence scores and picks the
    verdict with higher weighted confidence; ties default to
    ``hold`` so the system errs on the side of caution.

    The PortfolioManager :class:`AgentSpec` overrides this with an
    LLM call that reads the full debate transcript. We keep this
    deterministic fallback so the graph is exercisable in unit
    tests without an LLM.
    """
    bull = (state or {}).get("bull_argument") or {}
    bear = (state or {}).get("bear_argument") or {}
    bull_conf = float(bull.get("confidence", 0.0) or 0.0)
    bear_conf = float(bear.get("confidence", 0.0) or 0.0)
    proposed = (state or {}).get("proposed_alpha") or {}

    if bull_conf >= bear_conf and bull_conf > 0.55:
        action = proposed.get("action", "buy") or "buy"
        rationale = bull.get("rationale", "bull argument prevailed")
    elif bear_conf > bull_conf and bear_conf > 0.55:
        action = "sell" if proposed.get("action") == "buy" else "hold"
        rationale = bear.get("rationale", "bear argument prevailed")
    else:
        action = "hold"
        rationale = "no clear consensus between bull and bear arguments"

    state["debate_verdict"] = {
        "action": action,
        "rationale": rationale,
        "bull_confidence": bull_conf,
        "bear_confidence": bear_conf,
        "deterministic_fallback": True,
    }
    return state


def build_dialectical_debate_graph(
    *,
    use_langgraph: bool | None = None,
    checkpointer: RedisCheckpointer | None = None,
):
    """Compose the Bull/Bear/PortfolioManager pipeline.

    State flow (slots in :class:`AgentState`):

    - ``proposed_alpha`` (input — populated upstream by
      ``quant_generator`` / ``risk_simulator``).
    - ``simulation_verdict`` (input — populated upstream by
      ``risk_simulator``).
    - ``bull_argument`` ← ``research.bull_researcher``.
    - ``bear_argument`` ← ``research.bear_researcher``.
    - ``debate_verdict`` ← ``research.portfolio_manager`` (or the
      deterministic fallback).
    """
    nodes: list[tuple[str, NodeFn]] = [
        ("bull_researcher", _agent_node("research.bull_researcher", output_slot="bull_argument")),
        ("bear_researcher", _agent_node("research.bear_researcher", output_slot="bear_argument")),
        (
            "portfolio_manager",
            _portfolio_manager_with_agent("research.portfolio_manager"),
        ),
    ]
    if use_langgraph is False:
        return SequentialGraph(nodes, checkpointer=checkpointer)
    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - dep guard
        return SequentialGraph(nodes, checkpointer=checkpointer)

    graph = StateGraph(dict)
    for name, fn in nodes:
        graph.add_node(name, fn)
    # Bull and bear run concurrently in LangGraph (both depend only on
    # the upstream proposed_alpha + simulation_verdict slots), then
    # both feed the portfolio manager.
    graph.add_edge(START, "bull_researcher")
    graph.add_edge(START, "bear_researcher")
    graph.add_edge("bull_researcher", "portfolio_manager")
    graph.add_edge("bear_researcher", "portfolio_manager")
    graph.add_edge("portfolio_manager", END)
    try:
        compiled = graph.compile(checkpointer=checkpointer if checkpointer else None)
    except TypeError:
        compiled = graph.compile()
    return compiled


def _portfolio_manager_with_agent(spec_name: str) -> NodeFn:
    """Run the configured manager agent, falling back to the deterministic node.

    Avoids dropping the user into a None-verdict state when the spec
    is not yet defined or the LLM is unreachable. The fallback node
    explicitly tags ``deterministic_fallback=True`` so downstream
    consumers can branch on it for auditing.
    """
    agent_node = _agent_node(spec_name, output_slot="debate_verdict")

    def _node(state: AgentState) -> AgentState:
        try:
            updated = agent_node(state)
            verdict = (updated or {}).get("debate_verdict")
            if isinstance(verdict, dict) and verdict.get("action"):
                return updated
        except Exception:  # noqa: BLE001
            logger.debug("portfolio_manager agent failed; using deterministic synth", exc_info=True)
        return _portfolio_manager_node(state)

    _node.__name__ = "portfolio_manager_node"
    return _node


__all__ = [
    "build_dialectical_debate_graph",
]
