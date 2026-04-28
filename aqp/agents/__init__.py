"""Agentic layer — CrewAI crews, tools, memory, and the spec-driven runtime.

Two coexisting subsystems:

- **Legacy CrewAI**: ``aqp.agents.crew`` / ``aqp.agents.roles`` /
  ``aqp.agents.tools`` (kept for the existing research crew + UI flows).
- **Spec-driven**: :class:`aqp.agents.spec.AgentSpec` +
  :class:`aqp.agents.runtime.AgentRuntime` + :mod:`aqp.agents.registry`
  (the new Phase 3 / 4 surface used by the Research / Selection /
  Trader / Analysis teams). Built-in specs are registered at import
  time below so callers can simply ``get_agent_spec("research.equity")``
  without YAML.

Importing this module triggers the spec registration; lazy imports
guard against missing CrewAI installs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aqp.agents.registry import add_spec

# --- Phase 4: pre-register every built-in spec ----------------------------
try:
    from aqp.agents.analysis import (
        build_portfolio_analyst_spec,
        build_run_analyst_spec,
        build_step_analyst_spec,
    )
    from aqp.agents.research import (
        build_equity_researcher_spec,
        build_news_miner_spec,
        build_universe_selector_spec,
    )
    from aqp.agents.selection import build_stock_selector_spec
    from aqp.agents.trader import build_signal_emitter_spec

    for _builder in (
        build_news_miner_spec,
        build_equity_researcher_spec,
        build_universe_selector_spec,
        build_stock_selector_spec,
        build_signal_emitter_spec,
        build_step_analyst_spec,
        build_run_analyst_spec,
        build_portfolio_analyst_spec,
    ):
        try:
            add_spec(_builder())
        except Exception:  # pragma: no cover
            pass
except Exception:  # pragma: no cover - spec layer always installs cleanly
    pass


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
