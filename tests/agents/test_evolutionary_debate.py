"""Tests for :class:`EvolutionaryDebateAdapter` + deterministic critic checks."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.agents.orchestration.adapters.evolutionary_debate import (
    EvolutionaryDebateAdapter,
)
from aqp.agents.orchestration.types import AdapterContext, AdapterResult
from aqp.agents.runtime import AgentRunResult
from aqp.assistants.critic_checks import run_deterministic_critic


# ------------------------------------------------------------------
# Deterministic critic check tests
# ------------------------------------------------------------------


# Use a real DSL formula — ``Mean`` is a registered base operator and
# ``$close`` is rewritten to the FIELD_close handle by the validator.
_VALID_FORMULA = "Mean($close, 20)"


def test_critic_rejects_per_symbol_loop():
    proposal = {
        "formula": _VALID_FORMULA,
        "code": (
            "def f(df, universe):\n"
            "    for sym in universe:\n"
            "        df[sym] = df[sym].pct_change()\n"
            "    return df\n"
        ),
        "rationale": "max_position 0.05",
    }
    verdict = run_deterministic_critic(proposal)
    assert verdict.passed is False
    rules = {v["rule"] for v in verdict.violations}
    assert "no_per_symbol_loop" in rules


def test_critic_rejects_exec_eval():
    proposal = {
        "formula": _VALID_FORMULA,
        "code": "exec('print(1)')",
        "rationale": "max_position 0.05",
    }
    verdict = run_deterministic_critic(proposal)
    rules = {v["rule"] for v in verdict.violations}
    assert "no_dynamic_code_exec" in rules


def test_critic_rejects_datamcp_bypass_imports():
    proposal = {
        "formula": _VALID_FORMULA,
        "code": "from aqp.persistence.models_agents import AgentRunV2\n",
        "rationale": "max_position 0.05",
    }
    verdict = run_deterministic_critic(proposal)
    rules = {v["rule"] for v in verdict.violations}
    assert "no_bypass_import" in rules


def test_critic_rejects_router_complete_bypass():
    proposal = {
        "formula": _VALID_FORMULA,
        "code": "router_complete(provider='ollama', model='x', messages=[])\n",
        "rationale": "max_position 0.05",
    }
    verdict = run_deterministic_critic(proposal)
    rules = {v["rule"] for v in verdict.violations}
    assert "no_direct_llm_call" in rules


def test_critic_rejects_missing_risk_constraints():
    proposal = {
        "formula": _VALID_FORMULA,
        "rationale": "this is a great factor",
    }
    verdict = run_deterministic_critic(proposal)
    rules = {v["rule"] for v in verdict.violations}
    assert "missing_risk_hint" in rules


def test_critic_passes_clean_vectorised_proposal():
    proposal = {
        "formula": _VALID_FORMULA,
        "rationale": (
            "Mean over 20-day window. max_position 0.05, cost_bps 1, "
            "stop_loss 0.02"
        ),
    }
    verdict = run_deterministic_critic(proposal)
    assert verdict.passed, verdict.violations


# ------------------------------------------------------------------
# Adapter tests (mocked AgentRuntime)
# ------------------------------------------------------------------


@pytest.fixture
def adapter_context() -> AdapterContext:
    return AdapterContext(
        workflow_run_id="wf-1",
        workflow_spec_name="assistant.financial_analyst_team_evolutionary",
        request_id="req-1",
        extras={
            "max_rounds": 2,
            "params": {
                "proposer_agent": "assistant.evolutionary_proposer",
                "developer_agent": "assistant.evolutionary_developer",
                "critic_agent": "assistant.evolutionary_critic",
                "evaluator_agent": "assistant.evolutionary_evaluator",
                "formula_field": "formula",
                "rationale_field": "rationale",
                "require_risk_constraints": True,
            },
        },
    )


def _patch_agent_dispatch(monkeypatch, role_outputs: dict[str, dict[str, Any]]):
    """Stub :func:`get_agent_spec` + :class:`AgentRuntime` so each role
    returns a canned :class:`AgentRunResult` from ``role_outputs``."""

    class _StubAgentSpec:
        def __init__(self, name: str) -> None:
            self.name = name

    def _get_spec(name: str) -> _StubAgentSpec:
        return _StubAgentSpec(name)

    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec", _get_spec, raising=False
    )

    class _StubRuntime:
        def __init__(self, *, spec, **_kw):
            self._spec = spec

        def run(self, *, inputs):
            output = role_outputs.get(self._spec.name, {})
            return AgentRunResult(
                run_id=f"run-{self._spec.name}",
                spec_name=self._spec.name,
                status="completed",
                output=dict(output),
                cost_usd=0.1,
                n_calls=1,
                n_tool_calls=0,
                n_rag_hits=0,
            )

    monkeypatch.setattr(
        "aqp.agents.runtime.AgentRuntime", _StubRuntime, raising=False
    )


def test_adapter_accepts_clean_proposal(adapter_context, monkeypatch):
    role_outputs = {
        "assistant.evolutionary_proposer": {
            "name": "mean_close_20",
            "formula": _VALID_FORMULA,
            "rationale": "max_position 0.05, cost_bps 1.0, stop_loss 0.02",
        },
        "assistant.evolutionary_developer": {
            "name": "mean_close_20",
            "formula": _VALID_FORMULA,
            "rationale": "max_position 0.05, cost_bps 1.0, stop_loss 0.02",
        },
        "assistant.evolutionary_critic": {"passed": True, "analytical_critique": "ok"},
        "assistant.evolutionary_evaluator": {"decision": "accept", "score": 0.9},
    }
    _patch_agent_dispatch(monkeypatch, role_outputs)

    adapter = EvolutionaryDebateAdapter()
    result = adapter.invoke({}, adapter_context)
    assert isinstance(result, AdapterResult)
    assert result.status == AdapterResult.STATUS_COMPLETED
    assert result.state.get("evolutionary_accepted") is not None
    assert any(
        c.get("node") == "evaluator" and c.get("status") == "completed"
        for c in result.breadcrumbs
    )


def test_adapter_rejects_per_symbol_loops(adapter_context, monkeypatch):
    role_outputs = {
        "assistant.evolutionary_proposer": {
            "formula": _VALID_FORMULA,
            "rationale": "max_position 0.05",
        },
        "assistant.evolutionary_developer": {
            "formula": _VALID_FORMULA,
            "rationale": "max_position 0.05",
            "code": "for sym in universe:\n    df[sym] = df[sym].pct_change()\n",
        },
        "assistant.evolutionary_critic": {"passed": False},
        "assistant.evolutionary_evaluator": {"decision": "reject"},
    }
    _patch_agent_dispatch(monkeypatch, role_outputs)
    adapter = EvolutionaryDebateAdapter()
    result = adapter.invoke({}, adapter_context)
    assert result.status == AdapterResult.STATUS_COMPLETED
    # The deterministic critic should have rejected; loop continues
    # to next round, but with the same code we never accept.
    assert result.state.get("evolutionary_accepted") is None
    history = result.state.get("evolutionary_history") or []
    rejected = [r for r in history if r.get("status") == "rejected"]
    assert rejected, "expected at least one rejected round"


def test_adapter_returns_error_for_missing_role(monkeypatch):
    ctx = AdapterContext(
        workflow_run_id="wf-2",
        workflow_spec_name="assistant.bad",
        request_id="req-2",
        extras={"max_rounds": 1, "params": {}},
    )
    adapter = EvolutionaryDebateAdapter()
    result = adapter.invoke({}, ctx)
    assert result.status == AdapterResult.STATUS_ERROR
    assert "missing role" in (result.failure.message or "")


def test_adapter_halts_when_context_halt_check_fires(adapter_context, monkeypatch):
    halted_ref = {"called": 0}

    def _halt_check() -> bool:
        halted_ref["called"] += 1
        return halted_ref["called"] >= 1

    ctx = AdapterContext(
        workflow_run_id="wf-3",
        workflow_spec_name="assistant.financial_analyst_team_evolutionary",
        request_id="req-3",
        extras=adapter_context.extras,
        halt_check=_halt_check,
    )
    adapter = EvolutionaryDebateAdapter()
    result = adapter.invoke({}, ctx)
    assert result.status == AdapterResult.STATUS_HALTED
