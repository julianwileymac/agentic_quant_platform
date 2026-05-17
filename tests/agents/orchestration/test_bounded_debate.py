"""Phase 2 — bounded debate termination tests.

Covers:

- :func:`aqp.agents.graph.dialectical.build_dialectical_debate_graph`
  with ``max_rounds=1`` still produces the legacy 3-node SequentialGraph
  shape so older sites (and the Phase 0 invariant test) keep working.
- ``max_rounds=N`` (N>1) on the SequentialGraph fallback runs Bull +
  Bear N times then the portfolio manager once.
- The :class:`DialecticalDebateAdapter` enforces the cap defensively
  even if a hand-rigged state arrives with ``research_debate.count``
  already past ``2 * max_rounds``.
- The adapter falls back to :func:`_portfolio_manager_node` synth
  when the graph returns without a ``debate_verdict`` slot.
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.agents.graph.dialectical import (
    _BoundedDebateSequentialGraph,
    _portfolio_manager_node,
    build_dialectical_debate_graph,
)
from aqp.agents.orchestration import AdapterContext, AdapterResult
from aqp.agents.orchestration.adapters.debate_adapter import DialecticalDebateAdapter


def _stub_node_factory(slot: str, history_key: str):
    def _node(state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state[slot] = {"argument": "stub", "confidence": 0.7}
        debate = dict(state.get("research_debate") or {})
        debate.setdefault(history_key, []).append("stub")
        state["research_debate"] = debate
        return state

    return _node


def test_single_round_default_keeps_three_node_shape():
    """``max_rounds=1`` must keep the SequentialGraph fallback to the
    legacy three-node shape so the Phase 0 invariant survives.
    """
    graph = build_dialectical_debate_graph(use_langgraph=False, max_rounds=1)
    names = [name for name, _fn in graph.nodes]
    assert names == ["bull_researcher", "bear_researcher", "portfolio_manager"]


def test_multi_round_uses_bounded_sequential_graph():
    graph = build_dialectical_debate_graph(use_langgraph=False, max_rounds=3)
    assert isinstance(graph, _BoundedDebateSequentialGraph)
    assert graph.max_rounds == 3


def test_bounded_sequential_graph_runs_each_node_max_rounds_times(monkeypatch):
    """Stub the bull / bear / manager nodes and assert call counts."""
    bull_calls = {"n": 0}
    bear_calls = {"n": 0}
    mgr_calls = {"n": 0}

    def _bull(state: dict[str, Any]) -> dict[str, Any]:
        bull_calls["n"] += 1
        return _stub_node_factory("bull_argument", "bull_history")(state)

    def _bear(state: dict[str, Any]) -> dict[str, Any]:
        bear_calls["n"] += 1
        return _stub_node_factory("bear_argument", "bear_history")(state)

    def _mgr(state: dict[str, Any]) -> dict[str, Any]:
        mgr_calls["n"] += 1
        state = dict(state)
        state["debate_verdict"] = {"action": "hold", "rationale": "stub mgr"}
        return state

    graph = _BoundedDebateSequentialGraph(
        nodes=[
            ("bull_researcher", _bull),
            ("bear_researcher", _bear),
            ("portfolio_manager", _mgr),
        ],
        max_rounds=3,
    )
    out = graph.invoke({})
    assert bull_calls["n"] == 3
    assert bear_calls["n"] == 3
    assert mgr_calls["n"] == 1
    assert out["debate_verdict"]["action"] == "hold"
    assert out["research_debate"]["count"] == 6


def test_bounded_sequential_graph_stream_yields_frames_in_order():
    """``stream()`` must yield one frame per node call so the runtime
    can poll the halt-check between them.
    """
    bull = _stub_node_factory("bull_argument", "bull_history")
    bear = _stub_node_factory("bear_argument", "bear_history")

    def _mgr(state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["debate_verdict"] = {"action": "buy"}
        return state

    graph = _BoundedDebateSequentialGraph(
        nodes=[
            ("bull_researcher", bull),
            ("bear_researcher", bear),
            ("portfolio_manager", _mgr),
        ],
        max_rounds=2,
    )
    frames = list(graph.stream({}))
    node_order = []
    for frame in frames:
        node_order.extend(frame.keys())
    assert node_order == [
        "bull_researcher",
        "bear_researcher",
        "bull_researcher",
        "bear_researcher",
        "portfolio_manager",
    ]


def test_debate_adapter_enforces_cap_on_overflowed_state(monkeypatch):
    """If a future graph upgrade exceeds the cap, the adapter clips it
    back to ``2 * max_rounds`` so downstream nodes see the correct count.
    """

    class _OverflowGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return {
                "research_debate": {"count": 99},
                "debate_verdict": {"action": "buy"},
                "bull_argument": {},
                "bear_argument": {},
            }

    def _factory(*, use_langgraph=None, max_rounds=2):
        return _OverflowGraph()

    import aqp.agents.graph.dialectical as dialectical_mod
    import aqp.agents.orchestration.adapters.debate_adapter as adapter_mod

    monkeypatch.setattr(dialectical_mod, "build_dialectical_debate_graph", _factory)

    # Re-import to make sure the adapter sees the patched factory at lookup time.
    adapter = DialecticalDebateAdapter()
    ctx = AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
        extras={"max_rounds": 2},
    )
    result = adapter.invoke({}, ctx)
    assert result.status == AdapterResult.STATUS_COMPLETED
    # Cap is enforced: 2 * max_rounds (=4), not the upstream 99.
    assert result.state["research_debate"]["count"] == 4
    assert any(b["node"] == "round_cap_enforce" for b in result.breadcrumbs)


def test_debate_adapter_forces_judge_synth_when_verdict_missing(monkeypatch):
    """When the graph returns without a ``debate_verdict``, the adapter
    runs the deterministic :func:`_portfolio_manager_node` synth.
    """

    class _NoVerdictGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return {
                "research_debate": {"count": 2},
                "bull_argument": {"confidence": 0.8, "rationale": "bull rationale"},
                "bear_argument": {"confidence": 0.2},
                "proposed_alpha": {"action": "buy"},
            }

    def _factory(*, use_langgraph=None, max_rounds=2):
        return _NoVerdictGraph()

    import aqp.agents.graph.dialectical as dialectical_mod

    monkeypatch.setattr(dialectical_mod, "build_dialectical_debate_graph", _factory)

    adapter = DialecticalDebateAdapter()
    ctx = AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
        extras={"max_rounds": 2},
    )
    result = adapter.invoke({}, ctx)
    assert result.status == AdapterResult.STATUS_COMPLETED
    verdict = result.state.get("debate_verdict") or {}
    assert verdict.get("action") in {"buy", "sell", "hold"}
    assert any(b["node"] == "forced_judge_synth" for b in result.breadcrumbs)


def test_dialectical_builder_rejects_zero_max_rounds():
    with pytest.raises(ValueError):
        build_dialectical_debate_graph(use_langgraph=False, max_rounds=0)
