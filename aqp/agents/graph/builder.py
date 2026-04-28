"""Graph builders that compose registered :class:`AgentSpec`s.

Three canonical pipelines are exposed:

- :func:`build_research_graph` — news_miner → equity_researcher → universe_selector.
- :func:`build_trader_graph` — trader.signal_emitter → analysis.run.
- :func:`build_full_pipeline_graph` — research → selection → trader →
  analysis (Alpha-GPT three-stage loop).

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


__all__ = [
    "SequentialGraph",
    "build_full_pipeline_graph",
    "build_research_graph",
    "build_trader_graph",
]
