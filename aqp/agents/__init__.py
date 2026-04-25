"""Agentic layer — CrewAI crews, tools, and memory.

The ``crew`` / ``roles`` / ``tools`` submodules depend on CrewAI and
related extras; we import them lazily so teams that only need the
trader-crew domain types (``aqp.agents.trading``) or just the LLM
router don't have to install CrewAI. Users that pull the lazy symbols
out of ``aqp.agents`` get a friendly ImportError with install guidance.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "build_research_crew",
    "get_tool",
    "make_data_scout",
    "make_hypothesis_designer",
    "make_meta_agent",
    "make_performance_evaluator",
    "make_risk_controller",
    "make_strategy_backtester",
    "run_research_crew",
]


if TYPE_CHECKING:  # pragma: no cover - typing shim
    from aqp.agents.crew import build_research_crew, run_research_crew  # noqa: F401
    from aqp.agents.roles import (  # noqa: F401
        make_data_scout,
        make_hypothesis_designer,
        make_meta_agent,
        make_performance_evaluator,
        make_risk_controller,
        make_strategy_backtester,
    )
    from aqp.agents.tools import get_tool  # noqa: F401


def __getattr__(name: str) -> Any:
    """Lazy load CrewAI-backed symbols on first access."""
    if name in {"build_research_crew", "run_research_crew"}:
        from aqp.agents import crew

        return getattr(crew, name)
    if name in {
        "make_data_scout",
        "make_hypothesis_designer",
        "make_meta_agent",
        "make_performance_evaluator",
        "make_risk_controller",
        "make_strategy_backtester",
    }:
        from aqp.agents import roles

        return getattr(roles, name)
    if name == "get_tool":
        from aqp.agents.tools import get_tool as _get_tool

        return _get_tool
    raise AttributeError(f"module 'aqp.agents' has no attribute {name!r}")
