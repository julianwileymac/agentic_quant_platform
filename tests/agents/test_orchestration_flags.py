"""Phase 0 baseline test for the additive orchestration refactor.

Asserts two things:

1. The six new ``AQP_ORCHESTRATION_*`` knobs land on :class:`Settings`
   with the documented additive defaults (all ``False`` / sane
   numeric defaults).
2. Every existing :mod:`aqp.agents.graph.builder` factory returns the
   same node sequence regardless of the new flags. The new flags must
   be strictly additive — flipping any combination on or off may not
   change the node names produced by the five legacy builders.

This is the regression test the rollout doc (aqp_docs/orchestration-
refactor-rollout.md) refers operators to before they enable any
``orchestration_*`` flag.
"""
from __future__ import annotations

import pytest

from aqp.agents.graph.builder import (
    SequentialGraph,
    build_full_pipeline_graph,
    build_quant_research_pipeline_graph,
    build_research_debate_graph,
    build_research_graph,
    build_trader_graph,
)

# (alias, builder_callable, expected_node_names)
LEGACY_BUILDERS = [
    (
        "research",
        build_research_graph,
        ("news_miner", "equity_researcher", "universe_selector"),
    ),
    (
        "trader",
        build_trader_graph,
        ("trader_signal", "decision_log_trader", "run_analyst"),
    ),
    (
        "full_pipeline",
        build_full_pipeline_graph,
        (
            "news_miner",
            "equity_researcher",
            "universe_selector",
            "stock_selector",
            "trader_signal",
            "decision_log_trader",
            "run_analyst",
            "portfolio_analyst",
            "decision_log_portfolio",
        ),
    ),
    (
        "research_debate",
        build_research_debate_graph,
        (
            "market_monitor",
            "quant_generator",
            "risk_simulator",
            "emit_signal_event",
            "reject_decision_log",
        ),
    ),
    (
        "quant_research_pipeline",
        build_quant_research_pipeline_graph,
        (
            "composite_voter",
            "regime_analyst",
            "cointegration_analyst",
            "risk_simulator",
            "emit_signal_event",
            "reject_decision_log",
        ),
    ),
]


ORCHESTRATION_FLAGS = (
    "orchestration_studio_enabled",
    "orchestration_crew_adapter_enabled",
    "orchestration_fusion_enabled",
    "orchestration_schedule_enabled",
    "orchestration_workflow_versioning_enabled",
    "orchestration_kill_propagation_enabled",
)


def test_orchestration_flags_present_and_default_off():
    """Every new flag is on :class:`Settings` and defaults to ``False``."""
    from aqp.config import settings

    for flag in ORCHESTRATION_FLAGS:
        assert hasattr(settings, flag), f"missing AQP_{flag.upper()} on Settings"
        assert getattr(settings, flag) is False, f"{flag} must default off"


def test_orchestration_numeric_knobs_present_with_safe_defaults():
    """The numeric knobs land with the documented safe defaults."""
    from aqp.config import settings

    assert hasattr(settings, "orchestration_max_debate_rounds")
    assert int(settings.orchestration_max_debate_rounds) >= 1
    assert hasattr(settings, "orchestration_halt_check_timeout_seconds")
    assert float(settings.orchestration_halt_check_timeout_seconds) > 0


@pytest.mark.parametrize(
    "alias,builder,expected", LEGACY_BUILDERS, ids=lambda x: getattr(x, "__name__", str(x))
)
def test_legacy_builder_node_sequence_stable(alias, builder, expected):
    """Force the SequentialGraph fallback and assert node names + order.

    Using ``use_langgraph=False`` removes the optional LangGraph dep
    from the assertion surface — the underlying node list is what we
    care about (the LangGraph path uses the exact same list).
    """
    graph = builder(use_langgraph=False)
    assert isinstance(graph, SequentialGraph), (
        f"{alias}: expected SequentialGraph fallback when use_langgraph=False"
    )
    names = tuple(name for name, _fn in graph.nodes)
    assert names == expected, f"{alias}: node sequence drifted to {names!r}"


@pytest.mark.parametrize(
    "alias,builder,expected", LEGACY_BUILDERS, ids=lambda x: getattr(x, "__name__", str(x))
)
def test_legacy_builder_node_sequence_invariant_to_flags(
    alias, builder, expected, monkeypatch
):
    """Flipping every orchestration flag must NOT change the legacy node list.

    This is the core "strictly additive" guarantee: Phase 1+ work can
    only register new adapters / runtimes; it cannot rewire any of the
    five canonical builders.
    """
    from aqp.config import settings

    for flag in ORCHESTRATION_FLAGS:
        monkeypatch.setattr(settings, flag, True, raising=True)
    monkeypatch.setattr(settings, "orchestration_max_debate_rounds", 5, raising=True)

    graph = builder(use_langgraph=False)
    assert isinstance(graph, SequentialGraph)
    names = tuple(name for name, _fn in graph.nodes)
    assert names == expected, (
        f"{alias}: flipping flags must NOT change legacy node sequence; got {names!r}"
    )
