"""Additive orchestration control plane.

This package layers a pluggable adapter registry + ``WorkflowRuntime``
on top of the existing :mod:`aqp.agents.graph` builders, :class:`aqp.
agents.runtime.AgentRuntime`, and the DataMCP boundary. Every member
of this package is strictly additive — wiring it into the legacy
graph or runtime requires flipping one of the ``orchestration_*``
flags on :class:`aqp.config.settings.Settings`.

Public surface (Phase 1):

- :class:`OrchestrationAdapter` (in :mod:`aqp.agents.orchestration.base`)
  — abstract base every adapter subclasses. The metaclass auto-tags
  concrete subclasses with their ``adapter_kind`` and calls
  ``aqp.core.registry.register(kind="orchestration_adapter", ...)``.
- :data:`ADAPTER_KINDS` — the canonical sub-kind catalog mirrored by
  the seven adapters that ship in later phases.
- :func:`list_adapters` / :func:`get_adapter` (in
  :mod:`aqp.agents.orchestration.registry`) — discovery / lookup APIs.
- :class:`OrchestrationState` (in :mod:`aqp.agents.orchestration.state`)
  — `total=False` TypedDict that extends the existing
  :class:`aqp.agents.graph.state.AgentState` with workflow + adapter
  breadcrumb slots so existing nodes keep mutating it.
- :class:`AdapterContext` / :class:`AdapterResult` (in
  :mod:`aqp.agents.orchestration.types`) — typed per-call inputs and
  return contract used by ``WorkflowRuntime`` in Phase 2.

The Phase 2-6 deliverables (runtime, adapters, spec/persistence, halt
fan-out) layer on this surface; the registry contract here is the
single chokepoint they all hold to.
"""
from __future__ import annotations

from aqp.agents.orchestration.base import (
    OrchestrationAdapter,
    OrchestrationAdapterMeta,
)
from aqp.agents.orchestration.registry import (
    ADAPTER_KINDS,
    OrchestrationAdapterKind,
    get_adapter,
    list_adapter_aliases,
    list_adapters,
)
from aqp.agents.orchestration.runtime import (
    WorkflowRunResult,
    WorkflowRuntime,
)
from aqp.agents.orchestration.spec import (
    WorkflowGuardrails,
    WorkflowScheduleRef,
    WorkflowSpec,
    load_workflow_specs_from_dir,
)
from aqp.agents.orchestration.state import (
    OrchestrationState,
    empty_orchestration_state,
)
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
    HaltCheck,
)

__all__ = [
    "ADAPTER_KINDS",
    "AdapterContext",
    "AdapterFailure",
    "AdapterResult",
    "HaltCheck",
    "OrchestrationAdapter",
    "OrchestrationAdapterKind",
    "OrchestrationAdapterMeta",
    "OrchestrationState",
    "WorkflowGuardrails",
    "WorkflowRunResult",
    "WorkflowRuntime",
    "WorkflowScheduleRef",
    "WorkflowSpec",
    "empty_orchestration_state",
    "get_adapter",
    "list_adapter_aliases",
    "list_adapters",
    "load_workflow_specs_from_dir",
]
