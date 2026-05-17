"""Workflow-aware extension of :class:`aqp.agents.graph.state.AgentState`.

We keep the existing :class:`AgentState` ``TypedDict`` (``total=False``)
intact and add a sibling :class:`OrchestrationState` that declares the
additional workflow-level slots. Both shapes are structurally
compatible so any graph node written against ``AgentState`` continues
to work when handed an :class:`OrchestrationState`.

New slots:

- ``workflow_run_id``: stable id for the surrounding ``WorkflowRun``.
- ``workflow_spec_name`` / ``workflow_spec_version_id``: provenance.
- ``adapter_breadcrumbs``: ordered audit trail of every adapter
  transition (``alias``, ``node``, ``status``, ``duration_ms``,
  ``cost_usd``).
- ``halt_token``: per-run override that lets the runtime trip the
  halt-check without depending on the global kill-switch key.
- ``fusion_inputs`` / ``fusion_output``: contract for the Phase 4
  ``SignalFusionAdapter``.
- ``target_weights``: contract for the Phase 4
  ``WeightCentricExecutionAdapter`` consumed by
  :class:`aqp.rl.portfolio.pipeline.WeightCentricPipeline`.
- ``schedule_metadata``: opaque dict the Phase 3
  ``AutomationScheduleAdapter`` populates so downstream nodes can
  read scheduling provenance without ORM lookups.
"""
from __future__ import annotations

from typing import Any, TypedDict

from aqp.agents.graph.state import AgentState


class OrchestrationState(AgentState, total=False):
    """Extends :class:`AgentState` with workflow + adapter slots."""

    workflow_run_id: str
    workflow_spec_name: str
    workflow_spec_version_id: str | None
    adapter_breadcrumbs: list[dict[str, Any]]
    halt_token: bool
    fusion_inputs: dict[str, Any]
    fusion_output: dict[str, Any]
    target_weights: dict[str, float]
    schedule_metadata: dict[str, Any]


def empty_orchestration_state(**overrides: Any) -> OrchestrationState:
    """Return a new :class:`OrchestrationState` seeded with safe defaults.

    Adds the new workflow slots on top of the legacy ``AgentState``
    seed so existing nodes never see ``KeyError`` when reading a
    slot that hasn't been populated yet.
    """
    from aqp.agents.graph.state import empty_state

    base = empty_state()
    extras: OrchestrationState = {
        "workflow_run_id": "",
        "workflow_spec_name": "",
        "workflow_spec_version_id": None,
        "adapter_breadcrumbs": [],
        "halt_token": False,
        "fusion_inputs": {},
        "fusion_output": {},
        "target_weights": {},
        "schedule_metadata": {},
    }
    extras.update(base)  # type: ignore[arg-type]
    extras.update(overrides)  # type: ignore[arg-type]
    return extras


__all__ = [
    "OrchestrationState",
    "empty_orchestration_state",
]
