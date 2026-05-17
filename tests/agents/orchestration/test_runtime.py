"""Phase 2 — :class:`WorkflowRuntime` happy-path + failure-path tests.

Covers:

- Successful adapter invocation returns ``WorkflowRunResult(status="completed")``,
  populates ``adapter_breadcrumbs`` on the state, and aggregates the
  adapter's cost / call / duration counters.
- An adapter that raises is captured into ``status="error"`` with a
  clean breadcrumb instead of leaking an exception across the
  runtime boundary.
- The runtime always installs + restores the cooperative cancel hook
  on the :class:`aqp.agents.runtime` ContextVar so legacy
  ``AgentRuntime`` callers are never left with a stale hook.
- :class:`WorkflowSpec.snapshot_hash` is stable across identical spec
  payloads (the Phase 5 ``workflow_spec_versions`` registry uses
  this for idempotent dedupe).

The runtime is exercised with a hand-rolled fake adapter so the test
runs without LangGraph / CrewAI / Redis.
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.agents.orchestration import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
    OrchestrationAdapter,
    WorkflowRuntime,
    WorkflowSpec,
    empty_orchestration_state,
)
from aqp.agents.runtime import _COOPERATIVE_CANCEL_CHECK


class _OkAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "runtime_ok_adapter"

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        merged = dict(state)
        merged["test_marker"] = "hit"
        breadcrumb = {
            "adapter": self.adapter_alias,
            "node": "fake_node",
            "status": "ok",
            "duration_ms": 1.23,
        }
        merged.setdefault("adapter_breadcrumbs", []).append(breadcrumb)
        return AdapterResult(
            state=merged,
            status="completed",
            cost_usd=0.42,
            n_calls=2,
            n_tool_calls=1,
            n_rag_hits=3,
            duration_ms=12.5,
            breadcrumbs=[breadcrumb],
        )


class _BrokenAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "runtime_broken_adapter"

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        raise RuntimeError("simulated adapter failure")


class _HaltAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "runtime_halt_adapter"

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        return AdapterResult(
            state=state,
            status=AdapterResult.STATUS_HALTED,
            failure=AdapterFailure(message="adapter saw halt", kind="halted"),
        )


@pytest.fixture(autouse=True)
def _disable_kill_switch(monkeypatch):
    """Hermetic test: never let a real Redis kill-switch key bleed in."""
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: False,
    )


@pytest.fixture
def base_spec():
    return WorkflowSpec(
        name="test.runtime.spec",
        description="runtime unit test spec",
        adapter="runtime_ok_adapter",
        params={"a": 1},
    )


def test_runtime_happy_path_returns_completed_result(base_spec):
    runtime = WorkflowRuntime(
        base_spec,
        adapter=_OkAdapter(),
        spec_version_id="ver-1",
    )
    result = runtime.run(inputs={"prompt": "test"})
    assert result.status == "completed"
    assert result.spec_name == "test.runtime.spec"
    assert result.spec_version_id == "ver-1"
    assert result.cost_usd == pytest.approx(0.42)
    assert result.n_calls == 2
    assert result.n_tool_calls == 1
    assert result.n_rag_hits == 3
    # Breadcrumb propagated to both the result and the state.
    assert any(b["node"] == "fake_node" for b in result.breadcrumbs)
    assert result.state["test_marker"] == "hit"
    assert result.state["workflow_run_id"] == runtime.run_id
    assert result.state["workflow_spec_name"] == "test.runtime.spec"
    # Inputs merged into state.
    assert result.state["inputs"]["prompt"] == "test"


def test_runtime_captures_adapter_exception_as_error(base_spec):
    spec = base_spec.model_copy(update={"adapter": "runtime_broken_adapter"})
    runtime = WorkflowRuntime(spec, adapter=_BrokenAdapter())
    result = runtime.run()
    assert result.status == "error"
    assert "simulated adapter failure" in (result.error or "")
    # An error breadcrumb was appended so the studio can highlight the failure node.
    err_crumbs = [b for b in result.state["adapter_breadcrumbs"] if b["status"] == "error"]
    assert err_crumbs, "runtime must record an error breadcrumb for adapter failures"


def test_runtime_seeds_state_with_existing_state(base_spec):
    seed = empty_orchestration_state(vt_symbol="AAPL.US")
    runtime = WorkflowRuntime(base_spec, adapter=_OkAdapter())
    result = runtime.run(state=seed)
    assert result.state.get("vt_symbol") == "AAPL.US"


def test_runtime_restores_cooperative_cancel_hook(base_spec):
    """The runtime must reset the ContextVar token even on error."""
    before = _COOPERATIVE_CANCEL_CHECK.get()
    spec = base_spec.model_copy(update={"adapter": "runtime_broken_adapter"})
    runtime = WorkflowRuntime(spec, adapter=_BrokenAdapter())
    runtime.run()
    after = _COOPERATIVE_CANCEL_CHECK.get()
    assert before is None
    assert after is None


def test_runtime_propagates_halt_status_from_adapter(base_spec):
    spec = base_spec.model_copy(update={"adapter": "runtime_halt_adapter"})
    runtime = WorkflowRuntime(spec, adapter=_HaltAdapter())
    result = runtime.run()
    assert result.status == AdapterResult.STATUS_HALTED
    assert result.halted is True


def test_workflow_spec_snapshot_hash_is_stable():
    a = WorkflowSpec(name="x", adapter="LangGraphAdapter", params={"k": 1, "j": 2})
    b = WorkflowSpec(name="x", adapter="LangGraphAdapter", params={"j": 2, "k": 1})
    assert a.snapshot_hash() == b.snapshot_hash()


def test_workflow_spec_snapshot_hash_changes_when_payload_changes():
    a = WorkflowSpec(name="x", adapter="LangGraphAdapter")
    b = WorkflowSpec(name="x", adapter="LangGraphAdapter", description="changed")
    assert a.snapshot_hash() != b.snapshot_hash()


def test_workflow_spec_rejects_invalid_max_rounds():
    with pytest.raises(Exception):
        WorkflowSpec(name="x", adapter="LangGraphAdapter", max_rounds=0)
