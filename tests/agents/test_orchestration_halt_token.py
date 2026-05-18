"""Regression test for defect 3: per-run halt token must actually fire.

Before the fix, :meth:`WorkflowRuntime._is_halted` hardcoded
``should_halt({"halt_token": False})`` so the per-run halt path was
dead code. The fix wires three independent halt sources:

1. Global kill-switch via :func:`aqp.agents.graph.conditions.should_halt`
   reading the actual ``halt_token`` slot adapters mutate.
2. Per-run Redis flag at ``aqp:workflow:halt:<run_id>`` /
   ``aqp:assistant:halt:<run_id>`` that
   :func:`aqp.api.routes.workflows._halt_runs` sets.
3. The persisted ``WorkflowRun.halted`` column.
"""
from __future__ import annotations

from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.runtime import WorkflowRuntime
from aqp.agents.orchestration.spec import WorkflowSpec
from aqp.agents.orchestration.types import AdapterContext, AdapterResult


class _NoopAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "_halt_token_noop_adapter"

    def __init__(self) -> None:
        self.invoked = False

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        self.invoked = True
        return AdapterResult(state=dict(state))


def _make_spec() -> WorkflowSpec:
    return WorkflowSpec(
        name="defect3.halt", adapter="_halt_token_noop_adapter"
    )


def test_state_halt_token_triggers_halted_status(monkeypatch):
    """Mutating ``state['halt_token']`` halts via ``_state_ref``."""

    class _MutatingAdapter(OrchestrationAdapter):
        adapter_kind = "graph"
        adapter_alias = "_halt_mutator"

        def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
            # Mid-run mutation — adapters use this path to signal a
            # cooperative shutdown without going through Redis or the DB.
            state["halt_token"] = True
            return AdapterResult(state=dict(state))

    spec = _make_spec()
    adapter = _MutatingAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter)
    result = runtime.run()
    # The post-adapter halt-check sees the mutated state and converts
    # the run into a halted result.
    assert result.halted is True
    assert result.status == "halted"


def test_redis_halt_flag_blocks_in_flight_run(monkeypatch):
    """Redis flag at ``aqp:workflow:halt:<run_id>`` halts before adapter run."""
    spec = _make_spec()
    adapter = _NoopAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter, run_id="halt-run-redis")

    # Stub the redis-flag check so the test never touches a real broker.
    monkeypatch.setattr(runtime, "_redis_halt_flag_set", lambda: True)
    monkeypatch.setattr(runtime, "_db_halt_flag_set", lambda: False)

    result = runtime.run()
    assert result.halted is True
    assert result.status == "halted"
    assert adapter.invoked is False, "adapter must not run when halted before start"


def test_db_halt_flag_blocks_in_flight_run(monkeypatch):
    """DB-level ``WorkflowRun.halted`` halts before adapter run."""
    spec = _make_spec()
    adapter = _NoopAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter, run_id="halt-run-db")

    monkeypatch.setattr(runtime, "_redis_halt_flag_set", lambda: False)
    monkeypatch.setattr(runtime, "_db_halt_flag_set", lambda: True)

    result = runtime.run()
    assert result.halted is True
    assert result.status == "halted"


def test_no_halt_lets_run_complete(monkeypatch):
    spec = _make_spec()
    adapter = _NoopAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter)

    monkeypatch.setattr(runtime, "_redis_halt_flag_set", lambda: False)
    monkeypatch.setattr(runtime, "_db_halt_flag_set", lambda: False)

    result = runtime.run()
    assert result.halted is False
    assert result.status in ("completed", AdapterResult.STATUS_COMPLETED)
    assert adapter.invoked is True
