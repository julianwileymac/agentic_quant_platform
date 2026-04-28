"""Conditional routing predicates used by the LangGraph builders.

Mirrors TradingAgents' ``conditional_logic.py`` but generalised to AQP's
:class:`AgentState`. Each predicate returns the next node name (string)
that the graph should route to.
"""
from __future__ import annotations

from typing import Any

from aqp.agents.graph.state import AgentState


def should_continue_debate(
    state: AgentState,
    *,
    max_rounds: int = 2,
    bull_node: str = "research.bull",
    bear_node: str = "research.bear",
    judge_node: str = "research.manager",
) -> str:
    """Bull/Bear debate loop, falling through to the manager after N rounds."""
    debate = state.get("research_debate") or {}
    if int(debate.get("count", 0)) >= 2 * max_rounds:
        return judge_node
    current = str(debate.get("current_response") or "")
    return bear_node if current.lower().startswith("bull") else bull_node


def should_continue_risk(
    state: AgentState,
    *,
    max_rounds: int = 1,
    aggressive_node: str = "risk.aggressive",
    conservative_node: str = "risk.conservative",
    neutral_node: str = "risk.neutral",
    judge_node: str = "portfolio.manager",
) -> str:
    """Aggressive → Conservative → Neutral cycle until the round budget elapses."""
    debate = state.get("risk_debate") or {}
    if int(debate.get("count", 0)) >= 3 * max_rounds:
        return judge_node
    speaker = str(debate.get("latest_speaker") or "").lower()
    if speaker == "aggressive":
        return conservative_node
    if speaker == "conservative":
        return neutral_node
    return aggressive_node


def should_consult_rag(
    state: AgentState,
    *,
    threshold: int = 1,
    rag_node: str = "rag.consult",
    next_node: str = "default",
) -> str:
    """Skip RAG nodes once we've already accumulated ``threshold`` RAG hits."""
    if int(state.get("n_rag_hits") or 0) >= threshold:
        return next_node
    return rag_node


def has_kill_switch(state: AgentState) -> bool:
    """Return ``True`` when the runtime kill switch is engaged.

    Hooks into :data:`aqp.config.Settings.risk_kill_switch_key` via Redis
    when available; falls back to ``False`` on any error.
    """
    try:
        import redis  # type: ignore[import-not-found]

        from aqp.config import settings

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return bool(client.get(settings.risk_kill_switch_key))
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "has_kill_switch",
    "should_consult_rag",
    "should_continue_debate",
    "should_continue_risk",
]
