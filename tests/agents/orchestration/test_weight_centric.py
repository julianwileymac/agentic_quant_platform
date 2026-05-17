"""Phase 4 — :class:`WeightCentricExecutionAdapter` tests.

Covers:

- Adapter refuses without ``orchestration_fusion_enabled``.
- With the flag on, fusion output flows through
  :class:`aqp.rl.portfolio.pipeline.WeightCentricPipeline` and the
  resulting risk-overlaid ``target_weights`` land on the state.
- When the risk overlay shrinks gross exposure below the trigger
  threshold, ``state["risk_veto"]`` is set AND
  ``simulation_verdict["approved"]`` becomes ``False`` so the existing
  :func:`risk_simulator_approves` predicate routes to
  ``reject_decision_log`` (no SignalEvent produced).
- The ``build_dialectical_with_fusion_graph`` builder is gated by
  the flag.
"""
from __future__ import annotations

import pytest

from aqp.agents.orchestration import AdapterContext, AdapterResult
from aqp.agents.orchestration.adapters.weight_centric_adapter import (
    WeightCentricExecutionAdapter,
)


def _ctx(**extras_overrides) -> AdapterContext:
    return AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
        extras={"params": extras_overrides},
    )


def test_adapter_refuses_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", False, raising=True)
    result = WeightCentricExecutionAdapter().invoke({}, _ctx())
    assert result.status == AdapterResult.STATUS_ERROR
    assert result.failure is not None
    assert result.failure.kind == "policy"


def test_adapter_requires_fusion_output_first(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", True, raising=True)
    result = WeightCentricExecutionAdapter().invoke({}, _ctx())
    assert result.status == AdapterResult.STATUS_ERROR
    assert "fusion_output" in (result.failure.message or "")


def test_adapter_runs_pipeline_and_writes_target_weights(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", True, raising=True)
    state = {
        "fusion_output": {
            "target_weights": {"AAPL.US": 0.30, "MSFT.US": -0.15},
        },
        "universe": ["AAPL.US", "MSFT.US"],
    }
    result = WeightCentricExecutionAdapter().invoke(
        state, _ctx(max_position_pct=0.25, max_gross_exposure=1.0)
    )
    assert result.status == AdapterResult.STATUS_COMPLETED
    weights = result.state["target_weights"]
    assert set(weights.keys()) == {"AAPL.US", "MSFT.US"}
    # Per-symbol cap honored.
    for w in weights.values():
        assert abs(w) <= 0.25 + 1e-6
    history = result.state["weight_pipeline_history"]
    stages = [entry["stage"] for entry in history]
    assert stages == ["f_S", "f_A", "f_T", "f_R"]


def test_adapter_sets_risk_veto_when_overlay_truncates_gross(monkeypatch):
    """When the overlay halves gross exposure, the adapter sets
    ``risk_veto`` AND mirrors a False ``simulation_verdict.approved``
    so the existing :func:`risk_simulator_approves` predicate routes
    to ``reject_decision_log``.
    """
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", True, raising=True)
    # Massively over-leveraged fusion output — the overlay's default
    # ``max_position_pct=0.20`` will trigger the >50% truncation flag
    # the adapter checks for.
    state = {
        "fusion_output": {
            "target_weights": {
                "AAPL.US": 1.0,
                "MSFT.US": -1.0,
                "GOOG.US": 1.0,
                "TSLA.US": -1.0,
                "AMZN.US": 1.0,
            },
        },
        "universe": ["AAPL.US", "MSFT.US", "GOOG.US", "TSLA.US", "AMZN.US"],
    }
    result = WeightCentricExecutionAdapter().invoke(
        state, _ctx(max_position_pct=0.05, max_gross_exposure=0.10)
    )
    assert result.status == AdapterResult.STATUS_COMPLETED
    assert result.state["risk_veto"] is True
    verdict = result.state["simulation_verdict"]
    assert verdict["approved"] is False
    assert "risk_overlay_veto" in verdict["risk_breaches"]

    # Confirm the existing predicate routes to reject_decision_log.
    from aqp.agents.graph.conditions import risk_simulator_approves

    assert risk_simulator_approves(result.state) == "reject_decision_log"


def test_build_dialectical_with_fusion_graph_gated(monkeypatch):
    from aqp.agents.graph.builder import build_dialectical_with_fusion_graph
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", False, raising=True)
    with pytest.raises(RuntimeError, match="ORCHESTRATION_FUSION_ENABLED"):
        build_dialectical_with_fusion_graph(use_langgraph=False)


def test_build_dialectical_with_fusion_graph_node_sequence(monkeypatch):
    """When the flag is on, the SequentialGraph fallback contains the
    full debate -> fusion -> weight_centric -> emit/reject pipeline.
    """
    from aqp.agents.graph.builder import (
        SequentialGraph,
        build_dialectical_with_fusion_graph,
    )
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", True, raising=True)
    graph = build_dialectical_with_fusion_graph(use_langgraph=False)
    assert isinstance(graph, SequentialGraph)
    names = [name for name, _fn in graph.nodes]
    assert names == [
        "bull_researcher",
        "bear_researcher",
        "portfolio_manager",
        "fusion",
        "weight_centric",
        "emit_signal_event",
        "reject_decision_log",
    ]


def test_emit_signal_event_node_is_still_the_sole_producer():
    """Sanity check: the new builder still routes to the existing
    :func:`_emit_signal_event_node`, not a sibling we accidentally
    shipped under another name.
    """
    from aqp.agents.graph import builder as builder_mod

    src = open(builder_mod.__file__, encoding="utf-8").read()
    # Count `SignalEvent` constructor calls — should still be exactly one
    # (the one inside _emit_signal_event_node).
    assert src.count("SignalEvent(") == 1
