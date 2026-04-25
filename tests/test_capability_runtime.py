"""Tests for the agent capability runtime (tools / memory / guardrails)."""
from __future__ import annotations

import time

import pytest

from aqp.agents.capabilities import (
    AgentCapabilities,
    GuardrailSpec,
    McpServerSpec,
    MemorySpec,
)
from aqp.agents.capability_runtime import CapabilityRuntime, GuardrailViolation, McpClient


def test_capabilities_defaults_round_trip() -> None:
    caps = AgentCapabilities()
    payload = caps.model_dump()
    assert payload["tools"] == []
    assert payload["max_cost_usd"] == 1.0
    assert payload["max_calls"] == 20


def test_runtime_resolves_known_tool() -> None:
    caps = AgentCapabilities(tools=["news_digest", "fundamentals_snapshot"])
    runtime = CapabilityRuntime(caps)
    tools = runtime.tools()
    assert len(tools) >= 1
    assert all(hasattr(t, "name") or callable(t) for t in tools)


def test_runtime_skips_unknown_tool() -> None:
    caps = AgentCapabilities(tools=["does_not_exist_tool_xyz"])
    runtime = CapabilityRuntime(caps)
    # Skipped + warned, not raised.
    assert runtime.tools() == []


def test_guardrail_required_rationale_violation() -> None:
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(require_rationale=True)
    )
    runtime = CapabilityRuntime(caps)
    with pytest.raises(GuardrailViolation):
        runtime.validate_output({"action": "BUY"})


def test_guardrail_passes_with_rationale_and_summary() -> None:
    caps = AgentCapabilities(guardrails=GuardrailSpec(require_rationale=True))
    runtime = CapabilityRuntime(caps)
    out = runtime.validate_output({"action": "BUY", "rationale": "earnings beat"})
    assert out["action"] == "BUY"


def test_guardrail_jsonschema_required() -> None:
    schema = {"type": "object", "required": ["action", "size_pct"], "properties": {"action": {"type": "string"}, "size_pct": {"type": "number"}}}
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(output_schema=schema, require_rationale=False)
    )
    runtime = CapabilityRuntime(caps)
    runtime.validate_output({"action": "BUY", "size_pct": 0.1})
    with pytest.raises(GuardrailViolation):
        runtime.validate_output({"action": "BUY"})  # missing size_pct


def test_guardrail_pydantic_schema() -> None:
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(
            output_schema="aqp.agents.trading.types.AgentDecision",
            require_rationale=False,
        )
    )
    runtime = CapabilityRuntime(caps)
    valid = {
        "vt_symbol": "AAPL.NASDAQ",
        "timestamp": "2024-03-15T00:00:00",
        "action": "BUY",
        "size_pct": 0.1,
        "confidence": 0.7,
        "rating": "buy",
    }
    runtime.validate_output(valid)
    with pytest.raises(GuardrailViolation):
        runtime.validate_output({"vt_symbol": "AAPL.NASDAQ"})  # incomplete


def test_guardrail_forbidden_term() -> None:
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(
            forbidden_terms=["pump and dump"],
            require_rationale=False,
        )
    )
    runtime = CapabilityRuntime(caps)
    with pytest.raises(GuardrailViolation):
        runtime.validate_output({"rationale": "Classic pump and dump play"})


def test_guardrail_min_confidence() -> None:
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(min_confidence=0.6, require_rationale=False)
    )
    runtime = CapabilityRuntime(caps)
    with pytest.raises(GuardrailViolation):
        runtime.validate_output({"confidence": 0.4})
    runtime.validate_output({"confidence": 0.7})


def test_guardrail_pii_redact() -> None:
    caps = AgentCapabilities(
        guardrails=GuardrailSpec(pii_redact=True, require_rationale=False)
    )
    runtime = CapabilityRuntime(caps)
    out = runtime.validate_output(
        {"rationale": "Reach me at user@example.com or 555-12-3456"}
    )
    assert "[REDACTED-EMAIL]" in out["rationale"]
    assert "[REDACTED-SSN]" in out["rationale"]


def test_track_call_cost_budget() -> None:
    caps = AgentCapabilities(max_cost_usd=0.05)
    runtime = CapabilityRuntime(caps)
    runtime.track_call(cost_usd=0.02)
    runtime.track_call(cost_usd=0.02)
    with pytest.raises(GuardrailViolation):
        runtime.track_call(cost_usd=0.05)


def test_track_call_max_calls() -> None:
    caps = AgentCapabilities(max_calls=2, max_cost_usd=10.0)
    runtime = CapabilityRuntime(caps)
    runtime.track_call(cost_usd=0.0)
    runtime.track_call(cost_usd=0.0)
    with pytest.raises(GuardrailViolation):
        runtime.track_call(cost_usd=0.0)


def test_mcp_client_falls_back_when_sdk_absent() -> None:
    spec = McpServerSpec(name="test_server", command="nonexistent")
    client = McpClient(spec)
    # SDK isn't installed in CI; call should be a no-op returning None.
    result = client.call("any_tool", {"x": 1})
    assert result is None
    assert client.list_tools() == []


def test_runtime_memory_disabled() -> None:
    caps = AgentCapabilities(memory=MemorySpec(kind="none"))
    runtime = CapabilityRuntime(caps)
    assert runtime.memory() is None


def test_runtime_stats_shape() -> None:
    caps = AgentCapabilities(tools=["news_digest"])
    runtime = CapabilityRuntime(caps)
    stats = runtime.stats()
    assert "cost_usd" in stats
    assert "n_calls" in stats
    assert "tools" in stats
