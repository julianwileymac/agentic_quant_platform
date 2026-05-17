"""Per-call typed contract used by every :class:`OrchestrationAdapter`.

The two dataclasses here form the boundary the Phase 2 ``WorkflowRuntime``
holds to:

- :class:`AdapterContext` — request-scoped inputs handed to an
  adapter at the start of every transition (tenancy ids, halt
  callback, request_id). Adapters MUST treat this as read-only.
- :class:`AdapterResult` — what every adapter returns (the mutated
  state, plus a small telemetry envelope). The runtime aggregates
  these into the canonical ``WorkflowRunResult`` ledger row.

Both dataclasses are pure-Python with ``slots=True`` so they pass
through :func:`json.dumps` after :meth:`to_dict` without pulling in
``pydantic`` here. Adapters that need richer pydantic shapes can
construct them inside their bodies.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

HaltCheck = Callable[[], bool]
"""Zero-arg callable that returns ``True`` when the runtime must halt.

The Phase 2 ``WorkflowRuntime`` injects this so adapters can poll
without importing the global kill-switch path directly. The check
itself piggybacks on :func:`aqp.agents.graph.conditions.has_kill_switch`
plus the per-run halt token.
"""


@dataclass(slots=True)
class AdapterContext:
    """Read-only context every adapter receives.

    Attributes
    ----------
    workflow_run_id:
        Stable id used by ``WorkflowRuntime`` to correlate adapter
        outputs into a single replayable run.
    workflow_spec_name:
        Logical workflow alias (``WorkflowSpec.name``). Adapters
        should NOT mutate the spec; this is informational.
    request_id:
        Trace id forwarded into ``trace_step`` spans and the canonical
        ``_progress.emit`` frame.
    workspace_id / project_id:
        Tenancy stamps copied from the active
        :class:`aqp.auth.context.RequestContext`. New ``DataMCPTool``
        calls inside adapters must forward these.
    actor / actor_kind:
        Who triggered the run. Mirrors the ``MCPToolContext`` fields
        for cross-system correlation.
    halt_check:
        Callable the adapter should poll between long-running inner
        steps. Returning ``True`` means the runtime is shutting the
        workflow down; the adapter MUST raise / return with
        ``halted=True`` so the runtime can persist the halt status.
    extras:
        Free-form bag for adapter-specific seeds (e.g. CrewAI inputs).
    """

    workflow_run_id: str
    workflow_spec_name: str
    request_id: str
    workspace_id: str | None = None
    project_id: str | None = None
    actor: str | None = None
    actor_kind: str | None = None
    halt_check: HaltCheck | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    received_at: datetime = field(default_factory=datetime.utcnow)

    def is_halted(self) -> bool:
        """Convenience wrapper that returns ``False`` when no checker is wired."""
        if self.halt_check is None:
            return False
        try:
            return bool(self.halt_check())
        except Exception:  # noqa: BLE001 - never crash the adapter on the halt-path
            return False


@dataclass(slots=True)
class AdapterFailure:
    """Structured failure payload returned alongside an unsuccessful result.

    Adapters never raise across the runtime boundary; they return
    ``AdapterResult(status="error", failure=AdapterFailure(...))`` so
    the runtime can persist a partial ledger row without losing the
    upstream state.
    """

    message: str
    kind: Literal["error", "policy", "timeout", "halted", "guardrail"] = "error"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdapterResult:
    """Standardised return value for every :class:`OrchestrationAdapter`.

    Adapters return this so the runtime can aggregate telemetry, persist
    the ``workflow_runs`` ledger row, and respect the halt-token without
    holding to a specific adapter shape.

    Attributes
    ----------
    state:
        The (mutated) :class:`OrchestrationState` after the adapter has
        run. Adapters typically receive a state and return the same
        dict with new slots populated.
    status:
        ``completed`` on success, ``halted`` when the halt-check fired,
        ``error`` for any other failure. Mirrors the
        ``AgentRunV2.status`` vocabulary.
    cost_usd / n_calls / n_tool_calls / n_rag_hits:
        Telemetry the runtime aggregates into the run-level rollup.
        Defaults to zero for non-LLM adapters (e.g. fusion).
    breadcrumbs:
        Ordered ``(adapter_alias, node_name, status, duration_ms)``
        records the runtime appends onto the state's
        ``adapter_breadcrumbs`` slot.
    failure:
        Set when ``status != "completed"``.
    """

    STATUS_COMPLETED: ClassVar[str] = "completed"
    STATUS_HALTED: ClassVar[str] = "halted"
    STATUS_ERROR: ClassVar[str] = "error"

    state: Mapping[str, Any]
    status: str = STATUS_COMPLETED
    cost_usd: float = 0.0
    n_calls: int = 0
    n_tool_calls: int = 0
    n_rag_hits: int = 0
    duration_ms: float = 0.0
    breadcrumbs: list[dict[str, Any]] = field(default_factory=list)
    failure: AdapterFailure | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cost_usd": self.cost_usd,
            "n_calls": self.n_calls,
            "n_tool_calls": self.n_tool_calls,
            "n_rag_hits": self.n_rag_hits,
            "duration_ms": self.duration_ms,
            "breadcrumbs": list(self.breadcrumbs),
            "failure": (
                {
                    "message": self.failure.message,
                    "kind": self.failure.kind,
                    "details": dict(self.failure.details),
                }
                if self.failure is not None
                else None
            ),
        }


__all__ = [
    "AdapterContext",
    "AdapterFailure",
    "AdapterResult",
    "HaltCheck",
]
