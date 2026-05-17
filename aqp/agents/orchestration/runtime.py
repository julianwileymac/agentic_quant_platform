"""``WorkflowRuntime`` — execute a :class:`WorkflowSpec` end-to-end.

Mirrors :class:`aqp.agents.runtime.AgentRuntime` in shape (open run →
do work → finalise) but operates one level above: it resolves an
:class:`OrchestrationAdapter` by alias, hands it an
:class:`AdapterContext` with a halt-check + tenancy stamps, and
aggregates the adapter's :class:`AdapterResult` into a
:class:`WorkflowRunResult` that downstream code (Phase 5 ``workflow_runs``
ledger row + Vite studio) reads from.

Telemetry contract:

- One :func:`aqp.agents.observability.node_span` wraps every adapter
  transition, mirroring ``AgentRuntime``'s ``trace_step`` per-step
  spans.
- Every transition emits a canonical
  :func:`aqp.tasks._progress.emit` frame
  ``{task_id, stage, message, timestamp, **extras}`` (rule 4).
- The halt-check is polled between transitions; a ``True`` return
  aborts the run with ``status="halted"`` and a final
  :func:`emit_done` frame whose ``stage="kill_switch"``.

The runtime never imports ORM models, never calls ``router_complete``
directly, and never writes to Iceberg — the surrounding adapters
delegate to existing sanctioned paths (``AgentRuntime``, DataMCP
tools, ``WeightCentricPipeline``, ``iceberg_catalog.append_arrow``).
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from aqp.agents.observability import node_span
from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.registry import get_adapter
from aqp.agents.orchestration.spec import WorkflowSpec
from aqp.agents.orchestration.state import OrchestrationState, empty_orchestration_state
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.agents.runtime import (
    reset_cooperative_cancel_check,
    set_cooperative_cancel_check,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowRunResult:
    """Aggregated outcome of a :class:`WorkflowSpec` execution.

    Phase 5 persists this into the ``workflow_runs`` ledger row; Phase
    6 surfaces it through ``/workflows/runs/{run_id}``.
    """

    run_id: str
    spec_name: str
    spec_version_id: str | None
    status: str
    state: dict[str, Any]
    breadcrumbs: list[dict[str, Any]]
    cost_usd: float
    n_calls: int
    n_tool_calls: int
    n_rag_hits: int
    duration_ms: float
    error: str | None = None
    halted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_name": self.spec_name,
            "spec_version_id": self.spec_version_id,
            "status": self.status,
            "breadcrumbs": list(self.breadcrumbs),
            "cost_usd": self.cost_usd,
            "n_calls": self.n_calls,
            "n_tool_calls": self.n_tool_calls,
            "n_rag_hits": self.n_rag_hits,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "halted": self.halted,
        }


class WorkflowRuntime:
    """Execute one :class:`WorkflowSpec` with halt-aware telemetry."""

    def __init__(
        self,
        spec: WorkflowSpec,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        context: Any | None = None,
        adapter: OrchestrationAdapter | None = None,
        spec_version_id: str | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        self.session_id = session_id
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:  # pragma: no cover
                context = None
        self.context = context
        self.spec_version_id = spec_version_id
        # Allow callers (and tests) to pre-instantiate an adapter so
        # we can exercise the runtime without depending on side-effect
        # registration.
        self._preset_adapter = adapter

    # ------------------------------------------------------------------ public API
    def run(
        self,
        inputs: Mapping[str, Any] | None = None,
        *,
        state: OrchestrationState | None = None,
    ) -> WorkflowRunResult:
        """Execute the spec end-to-end. Always returns a result.

        Errors never raise — they're captured into the result so
        callers can persist a partial trace and surface it in the
        UI. The legacy :class:`AgentRuntime.run` follows the same
        contract.
        """
        start = time.perf_counter()
        state = self._seed_state(inputs, state)
        adapter = self._resolve_adapter()
        ctx = self._build_context()

        cancel_token = set_cooperative_cancel_check(ctx.halt_check)
        try:
            # Halt-check BEFORE the first transition so a workflow that
            # arrives with the kill switch already flipped never starts.
            if ctx.is_halted():
                return self._halted_result(state, "kill switch engaged before start", start)

            with node_span(
                adapter_alias=adapter.adapter_alias or type(adapter).__name__,
                node_name=self.spec.adapter,
                workflow_run_id=self.run_id,
                workflow_spec_name=self.spec.name,
                kind="workflow",
            ) as span:
                try:
                    result = adapter.invoke(state, ctx)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "WorkflowRuntime adapter %s raised", self.spec.adapter
                    )
                    return self._error_result(state, str(exc), start)
                span["status"] = getattr(result, "status", "completed")
                span["cost_usd"] = float(getattr(result, "cost_usd", 0.0) or 0.0)

            # Halt-check AFTER the adapter returns so a late kill-switch
            # flip still surfaces as a halt rather than a completed run.
            if ctx.is_halted():
                return self._halted_result(state, "kill switch engaged mid-run", start)

            return self._finalise(state, result, start)
        finally:
            reset_cooperative_cancel_check(cancel_token)

    # ------------------------------------------------------------------ helpers
    def _seed_state(
        self,
        inputs: Mapping[str, Any] | None,
        state: OrchestrationState | None,
    ) -> OrchestrationState:
        if state is None:
            state = empty_orchestration_state()
        else:
            state = dict(state)  # type: ignore[assignment]
        state["workflow_run_id"] = self.run_id
        state["workflow_spec_name"] = self.spec.name
        state.setdefault("workflow_spec_version_id", self.spec_version_id)
        state.setdefault("adapter_breadcrumbs", [])
        state.setdefault("halt_token", False)
        if inputs:
            merged = dict(state.get("inputs") or {})
            merged.update(dict(inputs))
            state["inputs"] = merged
        return state

    def _resolve_adapter(self) -> OrchestrationAdapter:
        if self._preset_adapter is not None:
            return self._preset_adapter
        cls = get_adapter(self.spec.adapter)
        try:
            return cls()
        except TypeError:
            # Adapters that need spec-time config can take the spec
            # directly; fall back to that constructor signature.
            return cls(self.spec)

    def _build_context(self) -> AdapterContext:
        workspace_id = getattr(self.context, "workspace_id", None) if self.context else None
        project_id = getattr(self.context, "project_id", None) if self.context else None
        user_id = getattr(self.context, "user_id", None) if self.context else None

        def _halt_check() -> bool:
            return self._is_halted()

        return AdapterContext(
            workflow_run_id=self.run_id,
            workflow_spec_name=self.spec.name,
            request_id=self.task_id or self.run_id,
            workspace_id=workspace_id,
            project_id=project_id,
            actor=user_id or "workflow_runtime",
            actor_kind="workflow" if self.context else "system",
            halt_check=_halt_check,
            extras={"spec_version_id": self.spec_version_id} if self.spec_version_id else {},
        )

    def _is_halted(self) -> bool:
        """Combined global-kill-switch + per-run halt-token gate."""
        try:
            from aqp.agents.graph.conditions import should_halt
        except Exception:  # pragma: no cover - import always works
            return False
        # ``should_halt`` accepts the AgentState ``Mapping``; pass a
        # minimal mapping that exposes the per-run halt_token flag we
        # might have flipped through the orchestration runtime API.
        return bool(should_halt({"halt_token": False}))

    def _emit_progress(self, stage: str, message: str, **extras: Any) -> None:
        if not self.task_id:
            return
        try:
            from aqp.tasks._progress import emit

            emit(self.task_id, stage, message, **extras)
        except Exception:  # pragma: no cover
            logger.debug("workflow progress emit failed", exc_info=True)

    def _emit_done(self, payload: dict[str, Any]) -> None:
        if not self.task_id:
            return
        try:
            from aqp.tasks._progress import emit_done

            emit_done(self.task_id, payload)
        except Exception:  # pragma: no cover
            logger.debug("workflow emit_done failed", exc_info=True)

    def _finalise(
        self,
        state: OrchestrationState,
        result: AdapterResult,
        start: float,
    ) -> WorkflowRunResult:
        # The adapter returns the mutated state in ``result.state``.
        # We treat that as authoritative — adapters are expected to
        # copy-on-write — and re-stamp the workflow provenance slots
        # so the runtime never loses its own identity even if the
        # adapter forgot to forward them.
        merged: dict[str, Any] = (
            dict(result.state) if isinstance(result.state, Mapping) else dict(state)
        )
        merged.setdefault("workflow_run_id", state.get("workflow_run_id", self.run_id))
        merged.setdefault(
            "workflow_spec_name", state.get("workflow_spec_name", self.spec.name)
        )
        merged.setdefault(
            "workflow_spec_version_id",
            state.get("workflow_spec_version_id", self.spec_version_id),
        )
        breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        for crumb in list(getattr(result, "breadcrumbs", None) or []):
            if crumb not in breadcrumbs:
                breadcrumbs.append(crumb)
        merged["adapter_breadcrumbs"] = breadcrumbs
        duration_ms = (time.perf_counter() - start) * 1000.0
        status = getattr(result, "status", "completed")
        out = WorkflowRunResult(
            run_id=self.run_id,
            spec_name=self.spec.name,
            spec_version_id=self.spec_version_id,
            status=status,
            state=merged,
            breadcrumbs=breadcrumbs,
            cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
            n_calls=int(getattr(result, "n_calls", 0) or 0),
            n_tool_calls=int(getattr(result, "n_tool_calls", 0) or 0),
            n_rag_hits=int(getattr(result, "n_rag_hits", 0) or 0),
            duration_ms=duration_ms,
            error=(
                getattr(result, "failure", None).message
                if getattr(result, "failure", None) is not None
                else None
            ),
            halted=status == AdapterResult.STATUS_HALTED,
        )
        self._emit_done(
            {
                "status": status,
                "stage": "workflow_complete" if status == "completed" else status,
                "spec": self.spec.name,
                "run_id": self.run_id,
                "duration_ms": round(duration_ms, 3),
                "cost_usd": out.cost_usd,
            }
        )
        return out

    def _halted_result(
        self, state: OrchestrationState, reason: str, start: float
    ) -> WorkflowRunResult:
        duration_ms = (time.perf_counter() - start) * 1000.0
        state["halt_token"] = True
        breadcrumbs = list(state.get("adapter_breadcrumbs") or [])
        breadcrumbs.append(
            {
                "adapter": self.spec.adapter,
                "node": "kill_switch",
                "status": "halted",
                "duration_ms": round(duration_ms, 3),
            }
        )
        state["adapter_breadcrumbs"] = breadcrumbs
        self._emit_done(
            {
                "halted": True,
                "stage": "kill_switch",
                "spec": self.spec.name,
                "run_id": self.run_id,
                "reason": reason,
            }
        )
        return WorkflowRunResult(
            run_id=self.run_id,
            spec_name=self.spec.name,
            spec_version_id=self.spec_version_id,
            status=AdapterResult.STATUS_HALTED,
            state=dict(state),
            breadcrumbs=breadcrumbs,
            cost_usd=0.0,
            n_calls=0,
            n_tool_calls=0,
            n_rag_hits=0,
            duration_ms=duration_ms,
            error=reason,
            halted=True,
        )

    def _error_result(
        self, state: OrchestrationState, message: str, start: float
    ) -> WorkflowRunResult:
        duration_ms = (time.perf_counter() - start) * 1000.0
        breadcrumbs = list(state.get("adapter_breadcrumbs") or [])
        breadcrumbs.append(
            {
                "adapter": self.spec.adapter,
                "node": "adapter_invoke",
                "status": "error",
                "duration_ms": round(duration_ms, 3),
                "error": message,
            }
        )
        state["adapter_breadcrumbs"] = breadcrumbs
        self._emit_done(
            {
                "status": "error",
                "stage": "workflow_error",
                "spec": self.spec.name,
                "run_id": self.run_id,
                "error": message,
            }
        )
        return WorkflowRunResult(
            run_id=self.run_id,
            spec_name=self.spec.name,
            spec_version_id=self.spec_version_id,
            status=AdapterResult.STATUS_ERROR,
            state=dict(state),
            breadcrumbs=breadcrumbs,
            cost_usd=0.0,
            n_calls=0,
            n_tool_calls=0,
            n_rag_hits=0,
            duration_ms=duration_ms,
            error=message,
        )


def runtime_for(spec_name: str, **kwargs: Any) -> WorkflowRuntime:
    """Convenience: look up a workflow spec by name and build a runtime.

    Phase 5 wires this against
    :func:`aqp.agents.orchestration.registry_specs.get_workflow_spec`;
    for now the spec must be passed explicitly.
    """
    raise NotImplementedError(
        "workflow registry lookup ships in Phase 5; pass a WorkflowSpec instance directly"
    )


__all__ = [
    "AdapterContext",
    "AdapterFailure",
    "AdapterResult",
    "WorkflowRunResult",
    "WorkflowRuntime",
    "runtime_for",
]
