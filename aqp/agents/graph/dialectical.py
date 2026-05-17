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
    max_rounds: int = 1,
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

    Bounded rounds (Phase 2 additive refactor)
    -----------------------------------------
    ``max_rounds`` defaults to ``1`` so the existing single-shot
    callers (every site that landed before the orchestration refactor)
    keep their original three-node ``bull → bear → portfolio_manager``
    shape — that path is what
    [tests/agents/test_orchestration_flags.py](../../tests/agents/test_orchestration_flags.py)
    pins as the legacy contract.

    Setting ``max_rounds >= 2`` opts into the bounded multi-round
    debate semantics needed by the ``DialecticalDebateAdapter`` that
    Phase 2 ships:

    * Each round runs Bull then Bear once, updates
      ``state["research_debate"]["count"]`` (the existing
      :class:`ResearchDebateState` slot), and routes back through
      :func:`aqp.agents.graph.conditions.should_continue_debate`.
    * Once ``count >= 2 * max_rounds`` the graph routes directly to
      ``portfolio_manager`` for the deterministic judge synthesis.
    * ``DialecticalDebateAdapter`` enforces the cap a second time in
      :class:`aqp.agents.orchestration.runtime.WorkflowRuntime` so a
      future LangGraph upgrade that ignores the predicate still
      cannot blow the budget.
    """
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1, got {max_rounds!r}")

    nodes: list[tuple[str, NodeFn]] = [
        ("bull_researcher", _agent_node("research.bull_researcher", output_slot="bull_argument")),
        ("bear_researcher", _agent_node("research.bear_researcher", output_slot="bear_argument")),
        (
            "portfolio_manager",
            _portfolio_manager_with_agent("research.portfolio_manager"),
        ),
    ]
    if use_langgraph is False:
        if max_rounds == 1:
            return SequentialGraph(nodes, checkpointer=checkpointer)
        return _BoundedDebateSequentialGraph(
            nodes,
            checkpointer=checkpointer,
            max_rounds=max_rounds,
        )
    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - dep guard
        if max_rounds == 1:
            return SequentialGraph(nodes, checkpointer=checkpointer)
        return _BoundedDebateSequentialGraph(
            nodes,
            checkpointer=checkpointer,
            max_rounds=max_rounds,
        )

    graph = StateGraph(dict)
    for name, fn in nodes:
        graph.add_node(name, fn)

    if max_rounds == 1:
        # Bull and bear run concurrently in LangGraph (both depend only on
        # the upstream proposed_alpha + simulation_verdict slots), then
        # both feed the portfolio manager.
        graph.add_edge(START, "bull_researcher")
        graph.add_edge(START, "bear_researcher")
        graph.add_edge("bull_researcher", "portfolio_manager")
        graph.add_edge("bear_researcher", "portfolio_manager")
        graph.add_edge("portfolio_manager", END)
    else:
        # Bounded rounds: Bull -> Bear -> conditional gate -> back to Bull
        # until ``should_continue_debate`` returns the manager node. The
        # gate's ``max_rounds`` arg matches the kwarg so the predicate
        # falls through deterministically.
        from aqp.agents.graph.conditions import should_continue_debate

        graph.add_edge(START, "bull_researcher")
        graph.add_edge("bull_researcher", "bear_researcher")
        graph.add_conditional_edges(
            "bear_researcher",
            lambda state: should_continue_debate(
                state,
                max_rounds=max_rounds,
                bull_node="bull_researcher",
                bear_node="bear_researcher",
                judge_node="portfolio_manager",
            ),
            {
                "bull_researcher": "bull_researcher",
                "bear_researcher": "bear_researcher",
                "portfolio_manager": "portfolio_manager",
            },
        )
        graph.add_edge("portfolio_manager", END)

    try:
        compiled = graph.compile(checkpointer=checkpointer if checkpointer else None)
    except TypeError:
        compiled = graph.compile()
    return compiled


class _BoundedDebateSequentialGraph(SequentialGraph):
    """Fallback runner that enforces ``max_rounds`` without LangGraph.

    Wraps the existing :class:`SequentialGraph` so the same
    :meth:`invoke` / :meth:`stream` signature stays intact. Loops
    Bull → Bear up to ``max_rounds`` times, updating the existing
    ``research_debate.count`` slot the conditional gate predicate
    reads, then runs the portfolio manager exactly once.
    """

    def __init__(
        self,
        nodes: list[tuple[str, "NodeFn"]],
        *,
        checkpointer: RedisCheckpointer | None = None,
        max_rounds: int = 2,
    ) -> None:
        super().__init__(nodes, checkpointer=checkpointer)
        self.max_rounds = max(1, int(max_rounds))
        self._node_map: dict[str, NodeFn] = dict(nodes)

    def invoke(self, state=None, *, thread_id=None):  # type: ignore[override]
        current = dict(state or {})
        debate = dict(current.get("research_debate") or {})
        debate.setdefault("count", 0)
        debate.setdefault("bull_history", [])
        debate.setdefault("bear_history", [])
        current["research_debate"] = debate

        for _ in range(self.max_rounds):
            current = self._node_map["bull_researcher"](current)
            debate = dict(current.get("research_debate") or debate)
            debate["count"] = int(debate.get("count", 0)) + 1
            current["research_debate"] = debate
            current = self._node_map["bear_researcher"](current)
            debate = dict(current.get("research_debate") or debate)
            debate["count"] = int(debate.get("count", 0)) + 1
            current["research_debate"] = debate

        current = self._node_map["portfolio_manager"](current)
        return current

    def stream(self, state=None, *, thread_id=None):  # type: ignore[override]
        current = dict(state or {})
        debate = dict(current.get("research_debate") or {})
        debate.setdefault("count", 0)
        debate.setdefault("bull_history", [])
        debate.setdefault("bear_history", [])
        current["research_debate"] = debate

        for _round in range(self.max_rounds):
            current = self._node_map["bull_researcher"](current)
            debate = dict(current.get("research_debate") or debate)
            debate["count"] = int(debate.get("count", 0)) + 1
            current["research_debate"] = debate
            yield {"bull_researcher": dict(current)}
            current = self._node_map["bear_researcher"](current)
            debate = dict(current.get("research_debate") or debate)
            debate["count"] = int(debate.get("count", 0)) + 1
            current["research_debate"] = debate
            yield {"bear_researcher": dict(current)}

        current = self._node_map["portfolio_manager"](current)
        yield {"portfolio_manager": dict(current)}


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
