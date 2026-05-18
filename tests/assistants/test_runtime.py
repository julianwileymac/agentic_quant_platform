"""``AssistantRuntime`` dispatch tests.

Mocks :class:`AgentRuntime` and :class:`WorkflowRuntime` so the tests
never touch Postgres / Redis / Iceberg / network. Verifies:

- ``mode='agent'`` dispatches to ``AgentRuntime`` and forwards
  ``AgentRunResult`` fields onto the assistant payload.
- ``mode='workflow'`` dispatches to ``WorkflowRuntime`` and forwards
  ``WorkflowRunResult`` fields.
- Errors during dispatch yield ``status='error'`` instead of raising.
- The pre-dispatch Redis halt flag is honoured.
"""
from __future__ import annotations

from typing import Any

from aqp.agents.runtime import AgentRunResult
from aqp.agents.spec import AgentSpec, ToolRef
from aqp.assistants.runtime import AssistantRuntime
from aqp.assistants.spec import (
    AssistantSpec,
    AssistantToolPolicy,
)


def _agent_assistant() -> AssistantSpec:
    return AssistantSpec(
        name="t.agent_dispatch",
        mode="agent",
        agent_spec_name="codebase_assistant",
        tool_policy=AssistantToolPolicy(read_only=True, allowed_tools=[]),
    )


def _workflow_assistant() -> AssistantSpec:
    return AssistantSpec(
        name="t.workflow_dispatch",
        mode="workflow",
        workflow_spec_name="assistant.financial_analyst_team_evolutionary",
    )


def _patch_persistence(monkeypatch) -> None:
    """No-op every persistence touch so the runtime never opens a DB session."""
    monkeypatch.setattr(
        AssistantRuntime, "_open_run", lambda self, **_kw: None, raising=False
    )
    monkeypatch.setattr(
        AssistantRuntime, "_persist_message", lambda self, **_kw: None, raising=False
    )
    monkeypatch.setattr(
        AssistantRuntime,
        "_record_event",
        lambda self, **_kw: None,
        raising=False,
    )

    def _finalise_passthrough(self, **kwargs):
        return {
            "run_id": self.run_id,
            "spec_name": self.spec.name,
            "status": kwargs.get("status"),
            "output": dict(kwargs.get("output") or {}),
            "error": kwargs.get("error"),
            "cost_usd": float(kwargs.get("cost_usd", 0.0) or 0.0),
            "n_calls": int(kwargs.get("n_calls", 0) or 0),
            "n_tool_calls": int(kwargs.get("n_tool_calls", 0) or 0),
            "n_rag_hits": int(kwargs.get("n_rag_hits", 0) or 0),
            "target_run_kind": kwargs.get("target_run_kind"),
            "target_run_id": kwargs.get("target_run_id"),
            "halted": bool(kwargs.get("halted", False)),
        }

    monkeypatch.setattr(AssistantRuntime, "_finalise", _finalise_passthrough, raising=False)
    monkeypatch.setattr(AssistantRuntime, "_emit", lambda self, *_a, **_kw: None, raising=False)


def test_agent_mode_dispatches_to_agent_runtime(monkeypatch):
    captured: dict[str, Any] = {}

    class _StubAgentRuntime:
        def __init__(self, *, spec, **kwargs):  # noqa: D401
            captured["spec"] = spec
            captured["kwargs"] = kwargs

        def run(self, *, inputs):
            captured["inputs"] = dict(inputs)
            return AgentRunResult(
                run_id="agent-run-1",
                spec_name=spec_passthrough.name,
                status="completed",
                output={"text": "hello"},
                cost_usd=0.5,
                n_calls=2,
                n_tool_calls=1,
                n_rag_hits=3,
            )

    spec_passthrough = AgentSpec(
        name="codebase_assistant",
        role="tester",
        tools=[ToolRef(name="codebase.search")],
    )

    monkeypatch.setattr(
        "aqp.agents.runtime.AgentRuntime", _StubAgentRuntime, raising=False
    )
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda *_args, **_kw: spec_passthrough,
        raising=False,
    )
    _patch_persistence(monkeypatch)

    runtime = AssistantRuntime(_agent_assistant())
    monkeypatch.setattr(runtime, "_redis_halt_set", lambda: False)
    payload = runtime.run(prompt="hi", inputs={"prompt": "hi"})

    assert payload["status"] == "completed"
    assert payload["output"] == {"text": "hello"}
    assert payload["cost_usd"] == 0.5
    assert payload["target_run_kind"] == "agent"
    assert payload["target_run_id"] == "agent-run-1"
    assert captured["inputs"]["prompt"] == "hi"


def test_workflow_mode_dispatches_to_workflow_runtime(monkeypatch):
    captured: dict[str, Any] = {}

    class _StubWorkflowResult:
        def __init__(self) -> None:
            self.run_id = "wf-run-1"
            self.status = "completed"
            self.state = {"summary": "done"}
            self.cost_usd = 1.25
            self.n_calls = 4
            self.n_tool_calls = 2
            self.n_rag_hits = 1
            self.breadcrumbs = [{"adapter": "x", "node": "y", "status": "ok"}]
            self.error = None
            self.halted = False

    class _StubWorkflowRuntime:
        def __init__(self, spec, **kwargs):
            captured["wf_spec"] = spec
            captured["wf_kwargs"] = kwargs

        def run(self, *, inputs):
            captured["wf_inputs"] = dict(inputs)
            return _StubWorkflowResult()

    class _StubWorkflowSpec:
        name = "assistant.financial_analyst_team_evolutionary"

    monkeypatch.setattr(
        "aqp.agents.orchestration.runtime.WorkflowRuntime",
        _StubWorkflowRuntime,
        raising=False,
    )
    monkeypatch.setattr(
        "aqp.agents.orchestration.registry_specs.get_workflow_spec",
        lambda *_a, **_kw: _StubWorkflowSpec(),
        raising=False,
    )
    monkeypatch.setattr(
        "aqp.agents.orchestration.registry_specs.persist_spec",
        lambda *_a, **_kw: None,
        raising=False,
    )
    _patch_persistence(monkeypatch)

    runtime = AssistantRuntime(_workflow_assistant())
    monkeypatch.setattr(runtime, "_redis_halt_set", lambda: False)
    payload = runtime.run(prompt="run team", inputs={"prompt": "run team"})

    assert payload["status"] == "completed"
    assert payload["target_run_kind"] == "workflow"
    assert payload["target_run_id"] == "wf-run-1"
    assert payload["cost_usd"] == 1.25
    assert payload["output"] == {"summary": "done"}


def test_redis_halt_short_circuits_dispatch(monkeypatch):
    _patch_persistence(monkeypatch)
    runtime = AssistantRuntime(_agent_assistant())
    monkeypatch.setattr(runtime, "_redis_halt_set", lambda: True)
    payload = runtime.run(prompt="ignored")
    assert payload["status"] == "halted"
    assert payload["halted"] is True


def test_runtime_swallows_dispatcher_exceptions(monkeypatch):
    _patch_persistence(monkeypatch)

    class _BoomRuntime:
        def __init__(self, **_kw): ...

        def run(self, *, inputs):
            raise RuntimeError("boom")

    spec_passthrough = AgentSpec(name="codebase_assistant", role="tester")
    monkeypatch.setattr(
        "aqp.agents.runtime.AgentRuntime", _BoomRuntime, raising=False
    )
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda *_a, **_kw: spec_passthrough,
        raising=False,
    )
    runtime = AssistantRuntime(_agent_assistant())
    monkeypatch.setattr(runtime, "_redis_halt_set", lambda: False)
    payload = runtime.run(prompt="hi")
    assert payload["status"] == "error"
    assert "boom" in (payload.get("error") or "")


def test_apply_tool_policy_filters_and_blocks_writes():
    runtime = AssistantRuntime(_agent_assistant())
    base_spec = AgentSpec(
        name="codebase_assistant",
        role="tester",
        tools=[
            ToolRef(name="codebase.search"),
            ToolRef(name="dangerous.write", scopes=["data:write"]),
        ],
    )
    runtime.spec.tool_policy = AssistantToolPolicy(
        read_only=True,
        allowed_tools=["codebase.search", "dangerous.write"],
        explicit_scopes=[],
    )
    new_spec = runtime._apply_tool_policy(base_spec)
    names = {ref.name for ref in new_spec.tools}
    assert names == {"codebase.search", "dangerous.write"}
    write_ref = next(t for t in new_spec.tools if t.name == "dangerous.write")
    assert "data:write" not in write_ref.scopes
