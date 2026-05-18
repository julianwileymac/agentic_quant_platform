"""Regression test for defect 2: WorkflowRuntime drops spec params.

Before the fix, :meth:`WorkflowRuntime._build_context` only forwarded
``spec_version_id`` into ``AdapterContext.extras``. ``WorkflowSpec.params``,
``max_rounds``, and ``guardrails`` never reached the adapter, so debate
/ fusion / graph adapters could not honour the spec-declared knobs and
silently fell back to hard-coded defaults.

The fix merges the three fields into ``extras`` while preserving
``spec_version_id`` and adds ``task_id`` for breadcrumbing.
"""
from __future__ import annotations

from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.runtime import WorkflowRuntime
from aqp.agents.orchestration.spec import WorkflowGuardrails, WorkflowSpec
from aqp.agents.orchestration.types import AdapterContext, AdapterResult


class _CapturingAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "_capturing_extras_adapter"

    def __init__(self) -> None:
        self.captured: AdapterContext | None = None

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        self.captured = context
        return AdapterResult(state=dict(state))


def _make_spec(**overrides: Any) -> WorkflowSpec:
    base = dict(
        name="defect2.extras",
        adapter="_capturing_extras_adapter",
        adapter_kind="graph",
        params={"builder": "full_pipeline", "agent_spec_bull": "research.bull"},
        max_rounds=4,
        guardrails=WorkflowGuardrails(
            cost_budget_usd=2.5, max_calls=50, max_duration_seconds=600
        ),
        annotations=["test", "defect2"],
    )
    base.update(overrides)
    return WorkflowSpec.model_validate(base)


def test_workflow_runtime_forwards_params_to_adapter():
    spec = _make_spec()
    adapter = _CapturingAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter, spec_version_id="abc123")
    runtime.run()

    assert adapter.captured is not None
    extras = adapter.captured.extras
    assert extras.get("spec_version_id") == "abc123"
    assert extras.get("max_rounds") == 4
    assert extras.get("params", {}).get("builder") == "full_pipeline"
    assert extras.get("params", {}).get("agent_spec_bull") == "research.bull"
    assert extras.get("guardrails", {}).get("cost_budget_usd") == 2.5
    assert extras.get("guardrails", {}).get("max_calls") == 50


def test_workflow_runtime_forwards_task_id():
    spec = _make_spec()
    adapter = _CapturingAdapter()
    runtime = WorkflowRuntime(
        spec, adapter=adapter, task_id="celery-task-xyz"
    )
    runtime.run()

    assert adapter.captured is not None
    assert adapter.captured.extras.get("task_id") == "celery-task-xyz"
    assert adapter.captured.request_id == "celery-task-xyz"


def test_workflow_runtime_handles_empty_params():
    """Empty ``params`` doesn't pollute extras with an empty dict."""
    spec = _make_spec(params={}, max_rounds=1)
    adapter = _CapturingAdapter()
    runtime = WorkflowRuntime(spec, adapter=adapter)
    runtime.run()

    assert adapter.captured is not None
    extras = adapter.captured.extras
    assert "params" not in extras
    assert extras.get("max_rounds") == 1
