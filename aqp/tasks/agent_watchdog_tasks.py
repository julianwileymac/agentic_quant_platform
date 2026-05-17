"""Agent stall watchdog — Celery beat task.

Scans :class:`AgentRunV2` for rows that ``AgentRuntime`` will never
close — either Celery dispatch dropped them on the floor (``pending``
forever) or the runtime hung mid-tool-loop without emitting any
:class:`AgentRunStep` rows. Halts them cleanly:

1. Revoke the linked Celery ``task_id`` with ``terminate=True``.
2. Update the row in-place: ``status='halted'``,
   ``error='watchdog:stalled'``, ``completed_at=now``.
3. Emit a canonical ``emit_done`` frame so any operator UI tailing
   the run sees the halt without a separate signal.

Hard rules honoured:

- **Rule 4 (Celery progress)** — every emit goes through
  :func:`emit / emit_done` in :mod:`aqp.tasks._progress`. The
  watchdog never publishes to Redis directly.
- **Rule 5 (Cross-task state)** — IDs are passed, ORM rows are
  re-fetched in the worker.
- **Rule 12 (AgentRuntime)** — the watchdog never constructs an
  :class:`AgentRuntime`. It only mutates the run-row status and
  revokes the Celery dispatch.
- **Rule 22 (DataMCP boundary)** — the matching read surface
  ``data.agents.health`` lives in
  :mod:`aqp.data.mcp.tools.agents`; agents never touch the ORM
  directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from aqp.tasks._progress import emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.utcnow()


def _settings() -> Any:
    from aqp.config import settings

    return settings


def _stall_threshold() -> timedelta:
    seconds = int(getattr(_settings(), "agent_stall_threshold_seconds", 300) or 300)
    return timedelta(seconds=max(30, seconds))


def _pending_grace() -> timedelta:
    # Pending rows get twice the threshold (a queued task is allowed
    # to wait longer before we declare it dead).
    return _stall_threshold() * 2


def _is_watchdog_enabled() -> bool:
    return bool(getattr(_settings(), "agent_watchdog_enabled", True))


def _revoke_celery_task(task_id: str | None) -> bool:
    """Best-effort ``app.control.revoke(task_id, terminate=True)``.

    Returns ``True`` when the revoke call succeeded (regardless of
    whether the task was actually running). Failures log + return
    ``False`` so the watchdog can still halt the DB row.
    """
    if not task_id:
        return False
    try:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("watchdog revoke failed for task_id=%s: %s", task_id, exc)
        return False


def _halt_row(row: Any, *, reason: str) -> dict[str, Any]:
    """Mutate a single :class:`AgentRunV2` row to ``status='halted'``."""
    task_id = getattr(row, "task_id", None)
    revoked = _revoke_celery_task(task_id)
    row.status = "halted"
    row.error = reason
    row.completed_at = _now()
    return {
        "run_id": str(row.id),
        "spec": getattr(row, "spec_name", ""),
        "task_id": task_id,
        "revoked": revoked,
        "reason": reason,
    }


def _last_step_at(session: Any, run_id: str) -> datetime | None:
    """Return the ``created_at`` of the latest step on ``run_id`` (or None)."""
    from aqp.persistence.models_agents import AgentRunStep

    row = (
        session.query(AgentRunStep.created_at)
        .filter(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.created_at.desc())
        .first()
    )
    if row is None:
        return None
    ts = row[0]
    if isinstance(ts, datetime):
        return ts
    return None


def _scan_and_halt() -> list[dict[str, Any]]:
    """Run the watchdog scan inside a single short DB session.

    Separated from the Celery task so we can call it directly from
    pytest without going through ``.delay``.
    """
    if not _is_watchdog_enabled():
        return []
    from aqp.persistence.db import get_session
    from aqp.persistence.models_agents import AgentRunV2

    now = _now()
    halted: list[dict[str, Any]] = []
    threshold = _stall_threshold()
    pending_grace = _pending_grace()

    with get_session() as session:
        candidates = (
            session.query(AgentRunV2)
            .filter(AgentRunV2.status.in_(("running", "pending")))
            .all()
        )
        for row in candidates:
            started_at = row.started_at or now
            age = now - started_at
            if row.status == "pending":
                if age > pending_grace:
                    halted.append(_halt_row(row, reason="watchdog:pending_stalled"))
                continue
            # status == "running"
            last_step = _last_step_at(session, row.id)
            anchor = last_step or started_at
            since_last = now - anchor
            if since_last > threshold:
                halted.append(_halt_row(row, reason="watchdog:stalled"))
        session.commit()

    # Emit done frames outside the DB session so a flaky broker can't
    # roll back the status update.
    for entry in halted:
        try:
            emit_done(entry["task_id"] or entry["run_id"], {
                "halted": True,
                "stage": "watchdog",
                "reason": entry["reason"],
                "run_id": entry["run_id"],
                "spec": entry["spec"],
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug("watchdog emit_done failed: %s", exc)
    return halted


@celery_app.task(bind=True, name="aqp.tasks.agent_watchdog_tasks.scan_for_stalled_agent_runs")
def scan_for_stalled_agent_runs(self) -> dict[str, Any]:
    task_id = self.request.id or "watchdog"
    try:
        halted = _scan_and_halt()
        return {
            "ok": True,
            "halted_count": len(halted),
            "halted": halted,
            "at": _now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent watchdog scan failed")
        emit_error(task_id, str(exc))
        raise


# ----------------------------------------------------------------------------
# Phase 6 of the additive orchestration refactor: workflow-run watchdog.
#
# Mirrors the agent watchdog above for ``workflow_runs`` rows produced by
# :class:`aqp.agents.orchestration.runtime.WorkflowRuntime`. Stays no-op
# when ``orchestration_kill_propagation_enabled`` is ``False`` so the
# scan is opt-in until the Phase 5 alembic migration has applied
# everywhere.
# ----------------------------------------------------------------------------


def _is_workflow_watchdog_enabled() -> bool:
    settings_obj = _settings()
    if not bool(
        getattr(settings_obj, "orchestration_kill_propagation_enabled", False)
    ):
        return False
    return bool(getattr(settings_obj, "agent_watchdog_enabled", True))


def _last_workflow_breadcrumb_at(row: Any) -> datetime | None:
    """Best-effort recency anchor for a workflow run.

    The workflow_runs.breadcrumbs JSON is an ordered list the runtime
    appends to per adapter transition; we treat the final crumb as
    the anchor (or fall back to started_at when no crumbs landed).
    """
    crumbs = getattr(row, "breadcrumbs", None) or []
    if not crumbs:
        return None
    last = crumbs[-1] if isinstance(crumbs, list) and crumbs else None
    if not isinstance(last, dict):
        return None
    ts = last.get("at") or last.get("created_at")
    if isinstance(ts, datetime):
        return ts
    return None


def _scan_and_halt_workflow_runs() -> list[dict[str, Any]]:
    """Halt stalled ``workflow_runs`` rows.

    Pattern parallels :func:`_scan_and_halt`. Stays defensive
    against the Phase 5 ORM not being installed yet — returns ``[]``
    instead of crashing the scheduler.
    """
    if not _is_workflow_watchdog_enabled():
        return []
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return []

    now = _now()
    halted: list[dict[str, Any]] = []
    threshold = _stall_threshold()
    pending_grace = _pending_grace()

    try:
        with get_session() as session:
            candidates = (
                session.query(WorkflowRun)
                .filter(WorkflowRun.status.in_(("running", "pending")))
                .all()
            )
            for row in candidates:
                started_at = row.started_at or now
                age = now - started_at
                if row.status == "pending":
                    if age > pending_grace:
                        entry = _halt_workflow_row(
                            row, reason="watchdog:workflow_pending_stalled"
                        )
                        halted.append(entry)
                    continue
                anchor = _last_workflow_breadcrumb_at(row) or started_at
                since_last = now - anchor
                if since_last > threshold:
                    entry = _halt_workflow_row(
                        row, reason="watchdog:workflow_stalled"
                    )
                    halted.append(entry)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("workflow watchdog scan failed: %s", exc, exc_info=True)
        return halted

    for entry in halted:
        try:
            emit_done(
                entry["task_id"] or entry["run_id"],
                {
                    "halted": True,
                    "stage": "watchdog",
                    "reason": entry["reason"],
                    "run_id": entry["run_id"],
                    "workflow": entry["workflow_spec_name"],
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("workflow watchdog emit_done failed: %s", exc)
    return halted


def _halt_workflow_row(row: Any, *, reason: str) -> dict[str, Any]:
    """Mutate a single ``workflow_runs`` row to ``status='halted'``."""
    task_id = getattr(row, "task_id", None)
    revoked = _revoke_celery_task(task_id)
    row.status = "halted"
    row.halted = True
    row.error = reason
    row.completed_at = _now()
    return {
        "run_id": str(row.id),
        "workflow_spec_name": getattr(row, "workflow_spec_name", ""),
        "task_id": task_id,
        "revoked": revoked,
        "reason": reason,
    }


def collect_workflow_health_snapshot() -> dict[str, Any]:
    """Read-only counts used by ``data.orchestration.health``.

    Degrades to an empty snapshot when the ORM isn't yet provisioned
    (same posture as the rest of the Phase 6 surface).
    """
    try:
        from sqlalchemy import func

        from aqp.persistence.db import get_session
        from aqp.persistence.models_workflows import WorkflowRun  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return {
            "running": 0,
            "pending": 0,
            "halted_last_24h": 0,
            "stalled_candidates": [],
            "stall_threshold_seconds": int(_stall_threshold().total_seconds()),
            "last_watchdog_at": _now().isoformat(),
            "table_present": False,
        }
    now = _now()
    threshold = _stall_threshold()
    pending_grace = _pending_grace()
    try:
        with get_session() as session:
            running = (
                session.query(func.count(WorkflowRun.id))
                .filter(WorkflowRun.status == "running")
                .scalar()
                or 0
            )
            pending = (
                session.query(func.count(WorkflowRun.id))
                .filter(WorkflowRun.status == "pending")
                .scalar()
                or 0
            )
            halted_last_24h = (
                session.query(func.count(WorkflowRun.id))
                .filter(WorkflowRun.status == "halted")
                .filter(WorkflowRun.completed_at >= now - timedelta(hours=24))
                .scalar()
                or 0
            )
            active_rows = (
                session.query(WorkflowRun)
                .filter(WorkflowRun.status.in_(("running", "pending")))
                .order_by(WorkflowRun.started_at.asc())
                .limit(50)
                .all()
            )
            stalled: list[dict[str, Any]] = []
            for row in active_rows:
                started_at = row.started_at or now
                age = (now - started_at).total_seconds()
                if row.status == "pending":
                    if age > pending_grace.total_seconds():
                        stalled.append(
                            {
                                "run_id": str(row.id),
                                "workflow_spec_name": getattr(
                                    row, "workflow_spec_name", ""
                                ),
                                "started_at": started_at.isoformat(),
                                "task_id": row.task_id,
                                "stalled_seconds": int(age),
                                "status": "pending",
                            }
                        )
                    continue
                anchor = _last_workflow_breadcrumb_at(row) or started_at
                since_last = (now - anchor).total_seconds()
                if since_last > threshold.total_seconds():
                    stalled.append(
                        {
                            "run_id": str(row.id),
                            "workflow_spec_name": getattr(
                                row, "workflow_spec_name", ""
                            ),
                            "started_at": started_at.isoformat(),
                            "task_id": row.task_id,
                            "stalled_seconds": int(since_last),
                            "status": "running",
                        }
                    )
    except Exception:  # noqa: BLE001
        logger.debug("collect_workflow_health_snapshot failed", exc_info=True)
        return {
            "running": 0,
            "pending": 0,
            "halted_last_24h": 0,
            "stalled_candidates": [],
            "stall_threshold_seconds": int(threshold.total_seconds()),
            "last_watchdog_at": _now().isoformat(),
            "table_present": False,
        }
    return {
        "running": int(running),
        "pending": int(pending),
        "halted_last_24h": int(halted_last_24h),
        "stalled_candidates": stalled,
        "stall_threshold_seconds": int(threshold.total_seconds()),
        "last_watchdog_at": _now().isoformat(),
        "table_present": True,
    }


def _scan_for_stalled_workflow_runs_impl(task_id: str) -> dict[str, Any]:
    """Underlying implementation — testable without Celery binding."""
    try:
        halted = _scan_and_halt_workflow_runs()
        return {
            "ok": True,
            "halted_count": len(halted),
            "halted": halted,
            "at": _now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow watchdog scan failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(
    bind=True,
    name="aqp.tasks.agent_watchdog_tasks.scan_for_stalled_workflow_runs",
)
def scan_for_stalled_workflow_runs(self) -> dict[str, Any]:
    """Celery wrapper — extracts ``self.request.id`` and forwards."""
    task_id = self.request.id or "workflow-watchdog"
    return _scan_for_stalled_workflow_runs_impl(task_id)


def collect_health_snapshot() -> dict[str, Any]:
    """Build the payload backing ``GET /agents/health``.

    Read-only — no mutations. Safe to call from a tight FastAPI poll
    loop and from the ``data.agents.health`` MCP tool.
    """
    from sqlalchemy import func

    from aqp.persistence.db import get_session
    from aqp.persistence.models_agents import AgentRunV2

    now = _now()
    threshold = _stall_threshold()
    pending_grace = _pending_grace()

    with get_session() as session:
        running = (
            session.query(func.count(AgentRunV2.id))
            .filter(AgentRunV2.status == "running")
            .scalar()
            or 0
        )
        pending = (
            session.query(func.count(AgentRunV2.id))
            .filter(AgentRunV2.status == "pending")
            .scalar()
            or 0
        )
        halted_last_24h = (
            session.query(func.count(AgentRunV2.id))
            .filter(AgentRunV2.status == "halted")
            .filter(AgentRunV2.completed_at >= now - timedelta(hours=24))
            .scalar()
            or 0
        )
        running_rows = (
            session.query(AgentRunV2)
            .filter(AgentRunV2.status.in_(("running", "pending")))
            .order_by(AgentRunV2.started_at.asc())
            .limit(50)
            .all()
        )
        stalled_candidates: list[dict[str, Any]] = []
        for row in running_rows:
            started_at = row.started_at or now
            age = (now - started_at).total_seconds()
            if row.status == "pending":
                if age > pending_grace.total_seconds():
                    stalled_candidates.append(
                        {
                            "run_id": str(row.id),
                            "spec": row.spec_name,
                            "started_at": started_at.isoformat(),
                            "task_id": row.task_id,
                            "stalled_seconds": int(age),
                            "status": "pending",
                        }
                    )
                continue
            last_step = _last_step_at(session, row.id)
            anchor = last_step or started_at
            since_last = (now - anchor).total_seconds()
            if since_last > threshold.total_seconds():
                stalled_candidates.append(
                    {
                        "run_id": str(row.id),
                        "spec": row.spec_name,
                        "started_at": started_at.isoformat(),
                        "task_id": row.task_id,
                        "stalled_seconds": int(since_last),
                        "status": "running",
                    }
                )

    return {
        "running": int(running),
        "pending": int(pending),
        "halted_last_24h": int(halted_last_24h),
        "stalled_candidates": stalled_candidates,
        "stall_threshold_seconds": int(threshold.total_seconds()),
        "last_watchdog_at": _now().isoformat(),
    }


__all__ = [
    "collect_health_snapshot",
    "collect_workflow_health_snapshot",
    "scan_for_stalled_agent_runs",
    "scan_for_stalled_workflow_runs",
    "_scan_and_halt",  # exported for tests
    "_scan_and_halt_workflow_runs",
    "_scan_for_stalled_workflow_runs_impl",
]
