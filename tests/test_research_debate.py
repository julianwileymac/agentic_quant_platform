from __future__ import annotations

from aqp.agents.graph.builder import _emit_signal_event_node
from aqp.agents.graph.conditions import risk_simulator_approves


def test_research_debate_gate_fails_closed() -> None:
    assert risk_simulator_approves({}) == "reject_decision_log"
    assert (
        risk_simulator_approves({"simulation_verdict": {"approved": False}})
        == "reject_decision_log"
    )
    assert (
        risk_simulator_approves(
            {
                "simulation_verdict": {
                    "approved": True,
                    "margin_check": {"has_headroom": False},
                }
            }
        )
        == "reject_decision_log"
    )


def test_research_debate_gate_approves_clean_verdict() -> None:
    state = {
        "simulation_verdict": {
            "approved": True,
            "insight_impact": {"approved": True},
            "margin_check": {"has_headroom": True},
            "risk_breaches": [],
        }
    }

    assert risk_simulator_approves(state) == "emit_signal_event"


def test_emit_signal_event_node_only_emits_when_approved() -> None:
    approved = {
        "proposed_alpha": {
            "vt_symbol": "SPY.NASDAQ",
            "direction": "long",
            "strength": 0.6,
            "confidence": 0.7,
            "horizon_days": 5,
            "rationale": "test",
        },
        "simulation_verdict": {"approved": True},
        "errors": [],
    }
    out = _emit_signal_event_node(approved)

    assert out["consensus_status"] == "approved_emitted"
    assert out["signal_event_emitted"]["event_type"] == "SIGNAL"
    assert out["signal_event_emitted"]["vt_symbol"] == "SPY.NASDAQ"

    rejected = {
        "proposed_alpha": {"vt_symbol": "SPY.NASDAQ"},
        "simulation_verdict": {"approved": False},
        "errors": [],
    }
    out = _emit_signal_event_node(rejected)
    assert out["consensus_status"] == "rejected"
    assert out.get("signal_event_emitted") is None
