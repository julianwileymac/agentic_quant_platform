"""Celery tasks for the Phase 3 orchestration control plane.

Two thin wrappers around :class:`aqp.agents.orchestration.WorkflowRuntime`:

- :func:`run_workflow` — primary entry point used by the API route in
  Phase 5 and the :class:`AutomationScheduleAdapter` in Phase 3.
- :func:`replay_run` — best-effort replay against a stored
  ``workflow_spec_version_id`` (no-ops cleanly when the Phase 5
  persistence tables aren't yet provisioned).

Both tasks:

- pass IDs only (rule 5), re-fetching the spec inside the worker;
- emit progress through :func:`aqp.tasks._progress.emit` /
  :func:`emit_done` / :func:`emit_error` (rule 4);
- never import ORM models at module top-level (rule for routes /
  tasks, mirrors :mod:`aqp.tasks.agent_tasks`);
- never call ``router_complete`` directly — that's the surrounding
  ``AgentRuntime``'s job inside the dispatched adapter.

The tasks are deliberately defensive: when the Phase 5 spec registry
isn't yet shipped (``orchestration_workflow_versioning_enabled=false``)
and no in-memory spec lookup is possible, we surface a clean
``emit_error`` instead of crashing the worker.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_workflow_impl(
    task_id: str,
    *,
    spec_version_id: str | None = None,
    spec_name: str | None = None,
    inputs: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    """Underlying implementation — testable without Celery binding.

    The Celery task wrapper :func:`run_workflow` is a 3-line shim
    that just forwards ``self.request.id`` here. Keeping the body in
    a plain function means unit tests can call this directly without
    monkeypatching the ``bind=True`` descriptor.
    """
    emit(
        task_id,
        "start",
        "Starting workflow",
        spec_name=spec_name,
        spec_version_id=spec_version_id,
        parent_run_id=parent_run_id,
    )

    try:
        spec = _resolve_spec(spec_version_id=spec_version_id, spec_name=spec_name)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"spec resolution failed: {exc}")
        raise

    if spec is None:
        msg = (
            "no spec resolvable from spec_version_id "
            f"{spec_version_id!r} / spec_name {spec_name!r}"
        )
        emit_error(task_id, msg)
        return {"ok": False, "error": msg}

    from aqp.agents.orchestration.runtime import WorkflowRuntime

    runtime = WorkflowRuntime(
        spec,
        task_id=task_id,
        spec_version_id=spec_version_id,
    )
    emit(task_id, "running", "Dispatching adapter", adapter=spec.adapter)
    try:
        result = runtime.run(inputs=inputs or {})
    except Exception as exc:  # noqa: BLE001
        logger.exception("orchestration_tasks.run_workflow crashed")
        emit_error(task_id, str(exc))
        raise

    payload = result.to_dict()
    payload["parent_run_id"] = parent_run_id
    emit_done(task_id, payload)
    return payload


def _replay_run_impl(task_id: str, run_id: str) -> dict[str, Any]:
    emit(task_id, "start", "Resolving workflow run for replay", run_id=run_id)
    try:
        snapshot = _load_run_snapshot(run_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"replay lookup failed: {exc}")
        raise

    if snapshot is None:
        msg = f"workflow run {run_id!r} not found (or table not provisioned)"
        emit_error(task_id, msg)
        return {"ok": False, "error": msg}

    emit(
        task_id, "dispatch", "Re-dispatching workflow", spec_name=snapshot.get("spec_name")
    )
    return _run_workflow_impl(
        task_id=task_id,
        spec_version_id=snapshot.get("spec_version_id"),
        spec_name=snapshot.get("spec_name"),
        inputs=snapshot.get("inputs") or {},
        parent_run_id=run_id,
    )


@celery_app.task(bind=True, name="aqp.tasks.orchestration_tasks.run_workflow")
def run_workflow(
    self,
    spec_version_id: str | None = None,
    spec_name: str | None = None,
    inputs: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    """Materialise + execute a :class:`WorkflowSpec` once.

    Resolves the spec in order:

    1. If ``spec_version_id`` is provided AND the Phase 5
       ``workflow_spec_versions`` table is reachable, hydrate the
       frozen payload (deterministic replay).
    2. Otherwise look the spec up by ``spec_name`` in the in-memory
       registry shipped by :mod:`aqp.agents.orchestration.registry_specs`
       (lands fully in Phase 5; Phase 3 ships a shim).
    3. If neither lookup succeeds, emit a clean error frame and return.

    The body is in :func:`_run_workflow_impl` so unit tests can exercise
    it without going through Celery's ``bind=True`` descriptor.
    """
    task_id = self.request.id or "local"
    return _run_workflow_impl(
        task_id,
        spec_version_id=spec_version_id,
        spec_name=spec_name,
        inputs=inputs,
        parent_run_id=parent_run_id,
    )


@celery_app.task(bind=True, name="aqp.tasks.orchestration_tasks.replay_run")
def replay_run(
    self,
    run_id: str,
) -> dict[str, Any]:
    """Re-execute a stored workflow run by its ``run_id``.

    Looks up the matching ``workflow_runs`` row, reconstructs the
    inputs, and re-dispatches with the same ``spec_version_id`` so
    replay semantics stay deterministic. When the Phase 5 persistence
    tables aren't yet provisioned this returns a clean
    ``ok=False`` payload instead of crashing the worker.
    """
    task_id = self.request.id or "local"
    return _replay_run_impl(task_id, run_id)


# ----------------------------------------------------------------------------
# Resolution helpers (defensive against Phase 5 tables not yet existing)
# ----------------------------------------------------------------------------


def _resolve_spec(
    *,
    spec_version_id: str | None,
    spec_name: str | None,
) -> Any | None:
    """Hydrate a :class:`WorkflowSpec` from version id or in-memory registry."""
    if spec_version_id:
        try:
            from aqp.agents.orchestration.registry_specs import (  # type: ignore[attr-defined]
                replay_workflow_spec_version,
            )

            return replay_workflow_spec_version(spec_version_id)
        except Exception:  # noqa: BLE001
            logger.debug(
                "workflow spec registry not yet available; falling back to spec_name lookup",
                exc_info=True,
            )

    if spec_name:
        try:
            from aqp.agents.orchestration.registry_specs import (  # type: ignore[attr-defined]
                get_workflow_spec,
            )

            return get_workflow_spec(spec_name)
        except Exception:  # noqa: BLE001
            logger.debug("workflow spec registry get_workflow_spec missing", exc_info=True)

    return None


def _load_run_snapshot(run_id: str) -> dict[str, Any] | None:
    """Best-effort lookup of a stored ``workflow_runs`` row."""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None
    try:
        with get_session() as session:
            row = (
                session.query(WorkflowRun)
                .filter(WorkflowRun.id == run_id)
                .one_or_none()
            )
            if row is None:
                return None
            return {
                "spec_name": getattr(row, "workflow_spec_name", None),
                "spec_version_id": getattr(row, "spec_version_id", None),
                "inputs": getattr(row, "inputs", None) or {},
            }
    except Exception:  # noqa: BLE001
        return None


__all__ = ["_replay_run_impl", "_run_workflow_impl", "replay_run", "run_workflow"]
