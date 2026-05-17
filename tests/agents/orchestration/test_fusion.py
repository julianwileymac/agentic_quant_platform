"""Phase 4 — deterministic fusion + :class:`SignalFusionAdapter`.

Covers:

- :func:`aqp.agents.trading.fusion.synthesize` is fully deterministic:
  identical :class:`FusionInputs` always produces identical
  :class:`FusionOutput`.
- Output target_weights respect L1 normalisation (gross exposure
  cap before the Phase 4 risk overlay).
- ``risk_overlay`` caps clip per-symbol weights as advertised.
- Missing contributors degrade gracefully (zero-symbol output is
  legal — no crash, no NaN).
- The :class:`SignalFusionAdapter` refuses without
  ``orchestration_fusion_enabled``.
- When enabled, the adapter writes ``fusion_inputs`` /
  ``fusion_output`` / ``target_weights`` onto the state without
  importing ORM models / calling router_complete.
"""
from __future__ import annotations

import inspect
import math

import pytest

from aqp.agents.orchestration import AdapterContext, AdapterResult
from aqp.agents.orchestration.adapters.fusion_adapter import SignalFusionAdapter
from aqp.agents.trading.fusion import FusionInputs, FusionOutput, synthesize


def test_synthesize_is_deterministic():
    """Same inputs -> identical output (no RNG, no time-dependent values)."""
    a = FusionInputs(
        quant_signals={"AAPL.US": 0.5, "MSFT.US": -0.3},
        debate_verdict={"action": "buy", "confidence": 0.7, "vt_symbol": "AAPL.US"},
        model_predictions={"AAPL.US": 0.2, "MSFT.US": -0.1},
        model_confidence=0.6,
        weights_prior={"quant": 0.5, "model": 0.3, "debate": 0.2},
    )
    out1 = synthesize(a)
    out2 = synthesize(a)
    assert out1.target_weights == out2.target_weights
    assert out1.confidence == out2.confidence
    assert out1.rationale == out2.rationale


def test_synthesize_l1_normalises_gross_exposure():
    out = synthesize(
        FusionInputs(quant_signals={"A": 1.0, "B": -1.0, "C": 0.5})
    )
    gross = sum(abs(v) for v in out.target_weights.values())
    assert gross <= 1.0 + 1e-9


def test_synthesize_risk_overlay_caps_per_symbol():
    out = synthesize(
        FusionInputs(
            quant_signals={"A": 1.0, "B": 0.001},
            risk_overlay={"max_position_pct": 0.10},
        )
    )
    for sym, w in out.target_weights.items():
        assert abs(w) <= 0.10 + 1e-9


def test_synthesize_with_no_contributors_returns_empty():
    out = synthesize(FusionInputs())
    assert out.target_weights == {}
    assert out.confidence == 0.0
    assert "no contributors" in out.rationale


def test_synthesize_combines_debate_and_quant():
    """A bull verdict on AAPL.US must push the combined AAPL weight long."""
    out = synthesize(
        FusionInputs(
            quant_signals={"AAPL.US": 0.4},
            debate_verdict={"action": "buy", "confidence": 0.8, "vt_symbol": "AAPL.US"},
        )
    )
    assert out.target_weights.get("AAPL.US", 0.0) > 0


def test_synthesize_rejects_non_finite_signals():
    """NaN / inf inputs must be dropped silently."""
    out = synthesize(
        FusionInputs(
            quant_signals={"A": math.inf, "B": float("nan"), "C": 0.5},
        )
    )
    assert "A" not in out.target_weights
    assert "B" not in out.target_weights
    assert "C" in out.target_weights


def test_fusion_output_to_dict_round_trips():
    out = synthesize(
        FusionInputs(quant_signals={"AAPL.US": 0.4, "MSFT.US": -0.2})
    )
    payload = out.to_dict()
    assert set(payload.keys()) == {"target_weights", "rationale", "confidence", "contributors"}


# ----------------------------------------------------------------------------
# Adapter tests
# ----------------------------------------------------------------------------


def _ctx(**extras_overrides) -> AdapterContext:
    return AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
        extras={"params": extras_overrides},
    )


def test_fusion_adapter_refuses_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", False, raising=True)
    result = SignalFusionAdapter().invoke({}, _ctx())
    assert result.status == AdapterResult.STATUS_ERROR
    assert result.failure is not None
    assert result.failure.kind == "policy"


def test_fusion_adapter_writes_output_to_state_when_enabled(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_fusion_enabled", True, raising=True)
    adapter = SignalFusionAdapter()
    state = {
        "quant_signals": {"AAPL.US": 0.4, "MSFT.US": -0.3},
        "debate_verdict": {
            "action": "buy",
            "confidence": 0.7,
            "vt_symbol": "AAPL.US",
        },
        "model_predictions": {"AAPL.US": 0.2},
    }
    result = adapter.invoke(state, _ctx(model_confidence=0.5))
    assert result.status == AdapterResult.STATUS_COMPLETED
    assert "fusion_inputs" in result.state
    assert "fusion_output" in result.state
    assert "target_weights" in result.state
    crumbs = result.state["adapter_breadcrumbs"]
    assert any(c["node"] == "fusion_synth" for c in crumbs)


def test_fusion_adapter_does_not_import_orm_or_router_complete():
    """Rule 22 + Rule 12: fusion module must not pull ORM / LLM router.

    Only inspects actual ``import`` statements via the ast module so
    docstrings + comments mentioning the rule names (which are
    legitimate cross-references) don't trip the check.
    """
    import ast

    for module_name in (
        "aqp.agents.trading.fusion",
        "aqp.agents.orchestration.adapters.fusion_adapter",
    ):
        mod = __import__(module_name, fromlist=["__file__"])
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                source = node.module or ""
                assert not source.startswith("aqp.persistence.models"), (
                    f"{module_name} imports {source}"
                )
                assert "iceberg_catalog" not in source, (
                    f"{module_name} imports {source}"
                )
                for alias in node.names:
                    assert alias.name != "router_complete", (
                        f"{module_name} imports router_complete from {source}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("aqp.persistence.models"), (
                        f"{module_name} imports {alias.name}"
                    )


@pytest.mark.parametrize(
    "verdict_action,expected_sign",
    [("buy", 1), ("sell", -1)],
)
def test_synth_respects_debate_verdict_direction(verdict_action, expected_sign):
    out = synthesize(
        FusionInputs(
            debate_verdict={
                "action": verdict_action,
                "confidence": 0.9,
                "vt_symbol": "FOO.US",
            }
        )
    )
    assert out.target_weights["FOO.US"] * expected_sign > 0
