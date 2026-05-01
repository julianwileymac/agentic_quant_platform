"""Graph builders that compose registered :class:`AgentSpec`s.

Four canonical pipelines are exposed:

- :func:`build_research_graph` — news_miner → equity_researcher → universe_selector.
- :func:`build_trader_graph` — trader.signal_emitter → analysis.run.
- :func:`build_full_pipeline_graph` — research → selection → trader →
  analysis (Alpha-GPT three-stage loop).
- :func:`build_research_debate_graph` — Phase 4 multi-agent consensus:
  Market Monitor → Quant Generator → Risk Simulator → consensus gate
  → emit_signal_event (or reject_decision_log). The only node that
  produces a SignalEvent on the Phase-1 event-driven engine bus is
  ``emit_signal_event``, and it ONLY runs when the Risk Simulator
  agent's ``simulation_verdict["approved"]`` is True.

When LangGraph is installed each builder returns a compiled
``StateGraph``; when it isn't (or the ``langgraph`` extra is omitted)
they return a :class:`SequentialGraph` that runs the same nodes in
order on the same :class:`AgentState`. The Sequential fallback is
deterministic, dependency-free, and used by the unit tests + cold
installs.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from aqp.agents.graph.checkpointer import RedisCheckpointer
from aqp.agents.graph.decision_log import append_pending_decision
from aqp.agents.graph.state import AgentState, empty_state

logger = logging.getLogger(__name__)


NodeFn = Callable[[AgentState], AgentState]


def _agent_node(spec_name: str, *, output_slot: str) -> NodeFn:
    """Build a node that runs ``spec_name`` via :class:`AgentRuntime` and
    stores the output in ``state[output_slot]``."""

    def _node(state: AgentState) -> AgentState:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        try:
            spec = get_agent_spec(spec_name)
        except KeyError:
            errs = list(state.get("errors") or [])
            errs.append(f"missing spec {spec_name}")
            state["errors"] = errs
            return state
        runtime = AgentRuntime(
            spec,
            run_id=state.get("run_id") or str(uuid.uuid4()),
            task_id=state.get("task_id"),
            session_id=state.get("session_id"),
        )
        result = runtime.run(_runtime_inputs(state))
        state[output_slot] = result.output  # type: ignore[literal-required]
        state["cost_usd"] = float(state.get("cost_usd") or 0.0) + result.cost_usd
        state["n_calls"] = int(state.get("n_calls") or 0) + result.n_calls
        state["n_rag_hits"] = int(state.get("n_rag_hits") or 0) + result.n_rag_hits
        if result.error:
            errs = list(state.get("errors") or [])
            errs.append(f"{spec_name}: {result.error}")
            state["errors"] = errs
        return state

    _node.__name__ = f"node_{spec_name.replace('.', '_')}"
    return _node


def _runtime_inputs(state: AgentState) -> dict[str, Any]:
    """Pluck the inputs the AgentRuntime should see."""
    out: dict[str, Any] = {}
    for k in ("vt_symbol", "as_of", "universe", "model_id", "strategy_id"):
        v = state.get(k)
        if v:
            out[k] = v
    extras = state.get("inputs") or {}
    if isinstance(extras, dict):
        out.update(extras)
    if "prompt" not in out:
        out["prompt"] = _render_default_prompt(state)
    return out


def _render_default_prompt(state: AgentState) -> str:
    parts: list[str] = []
    if state.get("vt_symbol"):
        parts.append(f"Symbol: {state['vt_symbol']}")
    if state.get("as_of"):
        parts.append(f"As of: {state['as_of']}")
    if state.get("universe"):
        parts.append(f"Universe: {','.join(state['universe'][:30])}")
    if state.get("model_id"):
        parts.append(f"Model: {state['model_id']}")
    if state.get("strategy_id"):
        parts.append(f"Strategy: {state['strategy_id']}")
    return ". ".join(parts) or "No explicit inputs."


def _decision_log_node(slot: str, spec_name: str) -> NodeFn:
    def _node(state: AgentState) -> AgentState:
        decision = state.get(slot) or {}
        if decision and state.get("vt_symbol"):
            try:
                append_pending_decision(
                    run_id=state.get("run_id") or "",
                    spec_name=spec_name,
                    vt_symbol=state.get("vt_symbol", ""),
                    as_of=state.get("as_of") or datetime.utcnow().isoformat(),
                    decision=decision,
                )
            except Exception:  # noqa: BLE001
                logger.debug("decision log node failed", exc_info=True)
        return state

    _node.__name__ = f"decision_log_{slot}"
    return _node


# ---------------------------------------------------------------------- Sequential fallback
class SequentialGraph:
    """Deterministic fallback when LangGraph isn't installed.

    Same ``invoke`` signature as a compiled LangGraph ``StateGraph`` so
    the rest of the runtime can stay agnostic.
    """

    def __init__(
        self,
        nodes: list[tuple[str, NodeFn]],
        *,
        checkpointer: RedisCheckpointer | None = None,
    ) -> None:
        self.nodes = list(nodes)
        self.checkpointer = checkpointer

    def invoke(self, state: AgentState | None = None, *, thread_id: str | None = None) -> AgentState:
        current: AgentState = dict(state or empty_state())
        if thread_id and self.checkpointer:
            head = self.checkpointer.load(thread_id)
            if head:
                current.update(head)
        run_id = current.get("run_id") or str(uuid.uuid4())
        current["run_id"] = run_id
        for name, fn in self.nodes:
            try:
                current = fn(current)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Node %s failed", name)
                errs = list(current.get("errors") or [])
                errs.append(f"{name}: {exc}")
                current["errors"] = errs
            if thread_id and self.checkpointer:
                self.checkpointer.save(thread_id, dict(current), step=name)
        return current

    def stream(
        self, state: AgentState | None = None, *, thread_id: str | None = None
    ) -> Iterable[dict[str, AgentState]]:
        """Mimic ``langgraph.compile().stream`` — yield one frame per node."""
        current: AgentState = dict(state or empty_state())
        if thread_id and self.checkpointer:
            head = self.checkpointer.load(thread_id)
            if head:
                current.update(head)
        run_id = current.get("run_id") or str(uuid.uuid4())
        current["run_id"] = run_id
        for name, fn in self.nodes:
            try:
                current = fn(current)
            except Exception as exc:  # noqa: BLE001
                errs = list(current.get("errors") or [])
                errs.append(f"{name}: {exc}")
                current["errors"] = errs
            if thread_id and self.checkpointer:
                self.checkpointer.save(thread_id, dict(current), step=name)
            yield {name: dict(current)}


# ---------------------------------------------------------------------- canonical builders
def build_research_graph(*, use_langgraph: bool | None = None, checkpointer: RedisCheckpointer | None = None):
    nodes = [
        ("news_miner", _agent_node("research.news_miner", output_slot="news_report")),
        ("equity_researcher", _agent_node("research.equity", output_slot="equity_report")),
        ("universe_selector", _agent_node("research.universe", output_slot="selection_report")),
    ]
    return _maybe_langgraph(nodes, use_langgraph=use_langgraph, checkpointer=checkpointer)


def build_trader_graph(*, use_langgraph: bool | None = None, checkpointer: RedisCheckpointer | None = None):
    nodes = [
        ("trader_signal", _agent_node("trader.signal_emitter", output_slot="trader_signal")),
        ("decision_log_trader", _decision_log_node("trader_signal", "trader.signal_emitter")),
        ("run_analyst", _agent_node("analysis.run", output_slot="risk_verdict")),
    ]
    return _maybe_langgraph(nodes, use_langgraph=use_langgraph, checkpointer=checkpointer)


def build_full_pipeline_graph(
    *, use_langgraph: bool | None = None, checkpointer: RedisCheckpointer | None = None
):
    """Alpha-GPT three-stage agentic loop: research → selection → trader → analysis."""
    nodes = [
        # Ideation
        ("news_miner", _agent_node("research.news_miner", output_slot="news_report")),
        ("equity_researcher", _agent_node("research.equity", output_slot="equity_report")),
        ("universe_selector", _agent_node("research.universe", output_slot="selection_report")),
        # Implementation
        ("stock_selector", _agent_node("selection.stock_selector", output_slot="investment_plan")),
        ("trader_signal", _agent_node("trader.signal_emitter", output_slot="trader_signal")),
        ("decision_log_trader", _decision_log_node("trader_signal", "trader.signal_emitter")),
        # Review
        ("run_analyst", _agent_node("analysis.run", output_slot="risk_verdict")),
        ("portfolio_analyst", _agent_node("analysis.portfolio", output_slot="portfolio_decision")),
        ("decision_log_portfolio", _decision_log_node("portfolio_decision", "analysis.portfolio")),
    ]
    return _maybe_langgraph(nodes, use_langgraph=use_langgraph, checkpointer=checkpointer)


def _emit_signal_event_node(state: AgentState) -> AgentState:
    """Translate the approved Quant-Generator insight into a Signal/SignalEvent.

    This is the ONLY node in any AQP graph that produces a SignalEvent for
    the Phase-1 event-driven engine. It refuses to emit if the consensus
    gate has not approved the insight (defence-in-depth — the gate
    predicate already routes around this node, but we re-check here so a
    direct-call failure mode also fails closed).
    """
    verdict = state.get("simulation_verdict") or {}
    if not isinstance(verdict, dict) or not bool(verdict.get("approved")):
        state["consensus_status"] = "rejected"
        return state

    insight = state.get("proposed_alpha") or {}
    if not isinstance(insight, dict) or "vt_symbol" not in insight:
        state["consensus_status"] = "malformed_insight"
        errs = list(state.get("errors") or [])
        errs.append("emit_signal_event: malformed proposed_alpha")
        state["errors"] = errs
        return state

    try:
        from datetime import datetime

        from aqp.core.types import Direction, Signal, SignalEvent, Symbol

        direction_str = str(insight.get("direction", "long")).lower()
        direction = Direction.LONG if direction_str == "long" else Direction.SHORT
        signal = Signal(
            symbol=Symbol.parse(insight["vt_symbol"]),
            strength=float(insight.get("strength", 0.5)),
            direction=direction,
            timestamp=datetime.utcnow(),
            confidence=float(insight.get("confidence", 0.5)),
            horizon_days=int(insight.get("horizon_days", 1)),
            source="research_debate",
            rationale=str(insight.get("rationale", "")),
        )
        event = SignalEvent(signals=[signal], timestamp=signal.timestamp)
        state["signal_event_emitted"] = {
            "vt_symbol": signal.symbol.vt_symbol,
            "direction": direction.value,
            "strength": signal.strength,
            "confidence": signal.confidence,
            "horizon_days": signal.horizon_days,
            "rationale": signal.rationale,
            "timestamp": str(signal.timestamp),
            "event_type": event.type.value,
        }
        state["consensus_status"] = "approved_emitted"
        # Mirror to the trader_signal slot so existing downstream consumers
        # (decision log, audit dashboards) see the same shape they're used to.
        state["trader_signal"] = state["signal_event_emitted"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("emit_signal_event failed")
        errs = list(state.get("errors") or [])
        errs.append(f"emit_signal_event: {exc}")
        state["errors"] = errs
        state["consensus_status"] = "emit_failed"
    return state


def _reject_decision_log_node(state: AgentState) -> AgentState:
    """Record a rejection on the decision log and short-circuit the graph.

    Carries enough rationale that the next loop's Quant Generator can
    incorporate the rejection feedback (e.g. "lower confidence next time
    because tvar_95 was 0.12, max 0.10").
    """
    state["consensus_status"] = "rejected"
    state["signal_event_emitted"] = {}
    verdict = state.get("simulation_verdict") or {}
    insight = state.get("proposed_alpha") or {}
    rationale = "no verdict"
    if isinstance(verdict, dict):
        rationale = str(verdict.get("rationale", "no rationale"))[:500]
    if isinstance(insight, dict) and insight.get("vt_symbol"):
        try:
            append_pending_decision(
                run_id=state.get("run_id") or "",
                spec_name="research.risk_simulator",
                vt_symbol=str(insight.get("vt_symbol", "")),
                as_of=state.get("as_of") or datetime.utcnow().isoformat(),
                decision={
                    "approved": False,
                    "consensus_status": "rejected",
                    "rationale": rationale,
                    "insight": insight,
                    "verdict": verdict,
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("reject_decision_log: append failed", exc_info=True)
    return state


def build_research_debate_graph(
    *,
    use_langgraph: bool | None = None,
    checkpointer: RedisCheckpointer | None = None,
):
    """Multi-agent consensus pipeline: monitor → generator → simulator → gate.

    State flow (slots in :class:`AgentState`):

    - ``regime_report``      ← ``research.market_monitor``
    - ``proposed_alpha``     ← ``research.quant_generator``
    - ``simulation_verdict`` ← ``research.risk_simulator``
    - ``signal_event_emitted`` ← ``emit_signal_event`` (only when approved)
    - ``consensus_status``   ← either ``"approved_emitted"`` or ``"rejected"``

    The LangGraph build wires a conditional edge after the Risk Simulator
    that routes to ``emit_signal_event`` only when
    :func:`risk_simulator_approves` returns ``"emit_signal_event"``;
    otherwise the graph short-circuits to ``reject_decision_log`` so the
    Phase-1 engine never sees an unverified insight.

    When LangGraph isn't installed the :class:`SequentialGraph` fallback
    runs every node in order — the conditional gate is implemented inside
    ``_emit_signal_event_node`` itself (it no-ops when the verdict isn't
    approved), so the same approval semantics hold.
    """
    nodes: list[tuple[str, NodeFn]] = [
        ("market_monitor", _agent_node("research.market_monitor", output_slot="regime_report")),
        ("quant_generator", _agent_node("research.quant_generator", output_slot="proposed_alpha")),
        ("risk_simulator", _agent_node("research.risk_simulator", output_slot="simulation_verdict")),
        ("emit_signal_event", _emit_signal_event_node),
        ("reject_decision_log", _reject_decision_log_node),
    ]
    if use_langgraph is False:
        return SequentialGraph(nodes, checkpointer=checkpointer)
    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]

        from aqp.agents.graph.conditions import risk_simulator_approves
    except Exception:  # pragma: no cover
        return SequentialGraph(nodes, checkpointer=checkpointer)
    graph = StateGraph(dict)
    for name, fn in nodes:
        graph.add_node(name, fn)
    graph.add_edge(START, "market_monitor")
    graph.add_edge("market_monitor", "quant_generator")
    graph.add_edge("quant_generator", "risk_simulator")
    graph.add_conditional_edges(
        "risk_simulator",
        risk_simulator_approves,
        {
            "emit_signal_event": "emit_signal_event",
            "reject_decision_log": "reject_decision_log",
        },
    )
    graph.add_edge("emit_signal_event", END)
    graph.add_edge("reject_decision_log", END)
    try:
        compiled = graph.compile(checkpointer=checkpointer if checkpointer else None)
    except TypeError:
        compiled = graph.compile()
    return compiled


# ---------------------------------------------------------------------- LangGraph wiring (optional)
def _maybe_langgraph(
    nodes: list[tuple[str, NodeFn]],
    *,
    use_langgraph: bool | None,
    checkpointer: RedisCheckpointer | None,
):
    if use_langgraph is False:
        return SequentialGraph(nodes, checkpointer=checkpointer)
    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover
        return SequentialGraph(nodes, checkpointer=checkpointer)
    graph = StateGraph(dict)
    for name, fn in nodes:
        graph.add_node(name, fn)
    if not nodes:
        return SequentialGraph(nodes, checkpointer=checkpointer)
    graph.add_edge(START, nodes[0][0])
    for prev, nxt in zip(nodes, nodes[1:], strict=False):
        graph.add_edge(prev[0], nxt[0])
    graph.add_edge(nodes[-1][0], END)
    try:
        compiled = graph.compile(checkpointer=checkpointer if checkpointer else None)
    except TypeError:
        compiled = graph.compile()
    return compiled


def build_quant_research_pipeline_graph(
    *,
    use_langgraph: bool | None = None,
    checkpointer: RedisCheckpointer | None = None,
):
    """Composite quant-research pipeline using the new rehydrated agents.

    Sequence:
    1. ``research.composite_voter`` — multi-indicator consensus.
    2. ``research.regime_analyst`` — ADX trend/range gate.
    3. ``research.cointegration_analyst`` — pair candidate analysis.
    4. ``research.risk_simulator`` — existing risk gate.
    5. Conditional emit (only when risk simulator approves).
    """
    nodes: list[tuple[str, NodeFn]] = [
        ("composite_voter", _agent_node("research.composite_voter", output_slot="vote_report")),
        ("regime_analyst", _agent_node("research.regime_analyst", output_slot="regime_report")),
        ("cointegration_analyst", _agent_node("research.cointegration_analyst", output_slot="cointegration_report")),
        ("risk_simulator", _agent_node("research.risk_simulator", output_slot="simulation_verdict")),
        ("emit_signal_event", _emit_signal_event_node),
        ("reject_decision_log", _reject_decision_log_node),
    ]
    if use_langgraph is False:
        return SequentialGraph(nodes, checkpointer=checkpointer)
    try:
        from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]

        from aqp.agents.graph.conditions import risk_simulator_approves
    except Exception:  # pragma: no cover
        return SequentialGraph(nodes, checkpointer=checkpointer)
    graph = StateGraph(dict)
    for name, fn in nodes:
        graph.add_node(name, fn)
    graph.add_edge(START, "composite_voter")
    graph.add_edge("composite_voter", "regime_analyst")
    graph.add_edge("regime_analyst", "cointegration_analyst")
    graph.add_edge("cointegration_analyst", "risk_simulator")
    graph.add_conditional_edges(
        "risk_simulator",
        risk_simulator_approves,
        {
            "emit_signal_event": "emit_signal_event",
            "reject_decision_log": "reject_decision_log",
        },
    )
    graph.add_edge("emit_signal_event", END)
    graph.add_edge("reject_decision_log", END)
    try:
        compiled = graph.compile(checkpointer=checkpointer if checkpointer else None)
    except TypeError:
        compiled = graph.compile()
    return compiled


__all__ = [
    "SequentialGraph",
    "build_full_pipeline_graph",
    "build_quant_research_pipeline_graph",
    "build_research_debate_graph",
    "build_research_graph",
    "build_trader_graph",
]
