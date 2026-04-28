"""Typed state shared across LangGraph nodes.

Mirrors TradingAgents' ``AgentState`` (``inspiration/TradingAgents-main/
tradingagents/agents/utils/agent_states.py``) but lifted to AQP's
spec-driven runtime: every node writes its output back into one of the
slots below so downstream nodes (and the post-hoc reflector) can read
a complete, structured trace without re-parsing markdown.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ResearchDebateState(TypedDict, total=False):
    bull_history: list[str]
    bear_history: list[str]
    current_response: str
    judge_decision: dict[str, Any]
    count: int


class RiskDebateState(TypedDict, total=False):
    aggressive_history: list[str]
    conservative_history: list[str]
    neutral_history: list[str]
    current_response: str
    latest_speaker: str
    count: int
    judge_decision: dict[str, Any]


class AgentState(TypedDict, total=False):
    """Shared state across every node in the agent graph."""

    # Identity
    run_id: str
    task_id: str
    session_id: str

    # Inputs
    vt_symbol: str
    as_of: str
    universe: list[str]
    model_id: str
    strategy_id: str
    inputs: dict[str, Any]

    # Reports (filled by analyst-style nodes)
    news_report: dict[str, Any]
    equity_report: dict[str, Any]
    fundamentals_report: dict[str, Any]
    technical_report: dict[str, Any]
    selection_report: dict[str, Any]

    # Decisions
    investment_plan: dict[str, Any]
    trader_signal: dict[str, Any]
    risk_verdict: dict[str, Any]
    portfolio_decision: dict[str, Any]

    # Debate / reflection
    research_debate: ResearchDebateState
    risk_debate: RiskDebateState
    past_context: list[str]

    # Telemetry
    cost_usd: float
    n_calls: int
    n_rag_hits: int
    errors: list[str]


def empty_state(**overrides: Any) -> AgentState:
    """Return an empty :class:`AgentState` with the given seed values."""
    base: AgentState = {
        "vt_symbol": "",
        "as_of": "",
        "universe": [],
        "model_id": "",
        "strategy_id": "",
        "inputs": {},
        "news_report": {},
        "equity_report": {},
        "fundamentals_report": {},
        "technical_report": {},
        "selection_report": {},
        "investment_plan": {},
        "trader_signal": {},
        "risk_verdict": {},
        "portfolio_decision": {},
        "research_debate": {"bull_history": [], "bear_history": [], "current_response": "", "count": 0},
        "risk_debate": {
            "aggressive_history": [],
            "conservative_history": [],
            "neutral_history": [],
            "current_response": "",
            "latest_speaker": "",
            "count": 0,
        },
        "past_context": [],
        "cost_usd": 0.0,
        "n_calls": 0,
        "n_rag_hits": 0,
        "errors": [],
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


__all__ = [
    "AgentState",
    "ResearchDebateState",
    "RiskDebateState",
    "empty_state",
]
