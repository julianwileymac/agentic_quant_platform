"""``AutomationScheduleAdapter`` — periodic workflow runs via Celery beat.

The adapter NEVER runs the workflow itself. It enqueues the Phase 3
``aqp.tasks.orchestration_tasks.run_workflow`` task on Celery, which
in turn instantiates a :class:`WorkflowRuntime` and dispatches to the
configured downstream adapter (Crew / LangGraph / Debate / ...).

Two invocation paths:

1. **Beat-driven** — :func:`register_schedule_with_celery_beat` mounts
   the adapter's schedule on the global ``celery_app.conf.beat_schedule``
   under a ``workflow-<slug>`` key. Operators inspect / disable via
   ``data.automation.list_schedules``.
2. **Inline** — :meth:`invoke` can be called directly from a
   :class:`WorkflowRuntime` step to fan out a child workflow run
   asynchronously, mirroring the ``daily_stock_analysis`` pattern in
   the inspiration repo of the same name.

Inspired by ``inspiration/daily_stock_analysis-main`` but routed
through AQP-safe primitives only — no bespoke threading / cron, no
direct ORM imports, no raw Redis writes.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


_BEAT_KEY_PREFIX = "workflow-"


def _slugify(name: str) -> str:
    """Lower-case, dash-joined slug used in operator-facing beat keys.

    Converts any non-alphanumeric character (including ``_`` and ``.``)
    into a single dash so beat keys read consistently in
    ``data.automation.list_schedules`` and grafana dashboards.
    """
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "workflow"


def beat_key_for_spec(spec_name: str) -> str:
    """Compose the canonical Celery beat key for a workflow spec name."""
    return f"{_BEAT_KEY_PREFIX}{_slugify(spec_name)}"


class AutomationScheduleAdapter(OrchestrationAdapter):
    """Enqueue ``aqp.tasks.orchestration_tasks.run_workflow`` for one run.

    Spec contract (when used inline)::

        adapter: AutomationScheduleAdapter
        params:
          target_spec_version_id: "..."   # required for replay-safe runs
          inputs: {}                      # forwarded into the child workflow
          countdown_seconds: 0            # delay before enqueue

    Spec contract (when used as a beat schedule)::

        adapter: AutomationScheduleAdapter
        schedule:
          interval_seconds: 86400
          enabled: true
        params:
          target_spec_name: "research.daily_stock_analysis_v1"
          inputs: {}

    The adapter only activates when
    ``settings.orchestration_schedule_enabled`` is ``True``. It still
    auto-registers (so the studio dropdown can show it) but
    :meth:`invoke` short-circuits to a policy-style failure when off.
    """

    adapter_kind = "schedule"
    adapter_alias = "AutomationScheduleAdapter"
    adapter_source = "daily_stock_analysis"
    adapter_category = "schedule"
    adapter_tags = ("celery_beat", "scheduler", "automation")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        if not getattr(settings, "orchestration_schedule_enabled", False):
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        "AutomationScheduleAdapter requires "
                        "AQP_ORCHESTRATION_SCHEDULE_ENABLED=true"
                    ),
                    kind="policy",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        params = context.extras.get("params") or {}
        target_spec_version_id = params.get("target_spec_version_id")
        target_spec_name = params.get("target_spec_name") or context.workflow_spec_name
        inputs = dict(params.get("inputs") or {})
        countdown = float(params.get("countdown_seconds") or 0.0)

        if context.is_halted():
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_HALTED,
                failure=AdapterFailure(
                    message="halt_check fired before schedule enqueue", kind="halted"
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        try:
            # Lazy import so the orchestration package keeps importing
            # cleanly in environments without a configured Celery broker.
            from aqp.tasks.orchestration_tasks import run_workflow

            async_result = run_workflow.apply_async(
                kwargs={
                    "spec_version_id": target_spec_version_id,
                    "spec_name": target_spec_name,
                    "inputs": inputs,
                    "parent_run_id": context.workflow_run_id,
                },
                countdown=countdown,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("AutomationScheduleAdapter enqueue failed")
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        merged = dict(state)
        merged.setdefault("schedule_metadata", {})
        merged["schedule_metadata"].update(
            {
                "scheduled_at": time.time(),
                "celery_task_id": str(getattr(async_result, "id", "")),
                "target_spec_name": target_spec_name,
                "target_spec_version_id": target_spec_version_id,
                "countdown_seconds": countdown,
                "parent_run_id": context.workflow_run_id,
            }
        )
        breadcrumb = {
            "adapter": self.adapter_alias,
            "node": f"enqueue:{target_spec_name}",
            "status": "ok",
            "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
            "celery_task_id": str(getattr(async_result, "id", "")),
        }
        existing_breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing_breadcrumbs + [breadcrumb]
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=[breadcrumb],
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )


def register_schedule_with_celery_beat(
    spec: Any,
    *,
    interval_seconds: float | None = None,
    cron: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> str | None:
    """Mount a workflow spec on the global ``celery_app.conf.beat_schedule``.

    Returns the beat-schedule key written, or ``None`` when the flag
    is off / the spec is invalid / Celery isn't importable. The Phase
    3 :func:`aqp.tasks.celery_app` boot path calls this for every
    YAML it discovers under ``configs/workflows/`` whose
    ``schedule.enabled`` is ``True``.

    Hard rule 4: registering a beat entry is NOT a progress emit; we
    don't touch ``_progress.publish`` here.
    """
    if not getattr(settings, "orchestration_schedule_enabled", False):
        logger.debug(
            "skipping beat schedule registration for %s: schedule flag off",
            getattr(spec, "name", spec),
        )
        return None
    try:
        from aqp.tasks.celery_app import celery_app
    except Exception:  # noqa: BLE001
        logger.debug("celery_app unavailable; skipping beat registration", exc_info=True)
        return None

    spec_name = getattr(spec, "name", None)
    if not spec_name:
        return None

    schedule: Any
    if interval_seconds is not None and interval_seconds > 0:
        schedule = float(interval_seconds)
    elif cron:
        try:
            from celery.schedules import crontab  # type: ignore[import-not-found]

            parts = cron.split()
            if len(parts) == 5:
                minute, hour, day_of_month, month_of_year, day_of_week = parts
                schedule = crontab(
                    minute=minute,
                    hour=hour,
                    day_of_month=day_of_month,
                    month_of_year=month_of_year,
                    day_of_week=day_of_week,
                )
            else:
                logger.warning("invalid cron expression for %s: %s", spec_name, cron)
                return None
        except Exception:  # noqa: BLE001
            logger.debug("crontab unavailable", exc_info=True)
            return None
    else:
        return None

    key = beat_key_for_spec(spec_name)
    celery_app.conf.beat_schedule[key] = {
        "task": "aqp.tasks.orchestration_tasks.run_workflow",
        "schedule": schedule,
        "kwargs": {
            "spec_name": spec_name,
            "spec_version_id": getattr(spec, "spec_version_id", None),
            "inputs": dict(inputs or {}),
        },
    }
    return key


__all__ = [
    "AutomationScheduleAdapter",
    "beat_key_for_spec",
    "register_schedule_with_celery_beat",
]
