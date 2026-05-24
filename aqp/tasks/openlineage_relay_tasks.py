"""OpenLineage relay Celery beat task (Workstream B).

Drains the :class:`OpenLineageOutbox` queue by POSTing each pending
row's payload to Marquez. Failures (Marquez 5xx, network error, missing
URL) leave the row in the outbox so the next pass picks it up; the
``attempts`` column lets operators identify stuck rows.

Hard rules honoured:

- **Rule 4 (Celery progress)** — every emit goes through
  :func:`emit` / :func:`emit_done` / :func:`emit_error` in
  :mod:`aqp.tasks._progress`. The task never publishes to Redis
  directly.
- **Rule 5 (Cross-task state)** — Postgres is the source of truth;
  the task is idempotent because rows are content-addressed by id.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _relay_enabled() -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, "lineage_openlineage_relay_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def _impl(task_id: str) -> dict[str, Any]:
    if not _relay_enabled():
        emit_done(
            task_id,
            {"ok": True, "skipped": True, "reason": "relay_disabled"},
        )
        return {"ok": True, "skipped": True}

    emit(task_id, "drain", "draining openlineage outbox")
    try:
        from aqp.lineage.openlineage.relay import drain_outbox_once

        summary = drain_outbox_once()
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, str(exc))
        logger.exception("openlineage relay drain failed")
        raise
    emit_done(task_id, summary)
    return {"ok": True, **summary}


@celery_app.task(
    bind=True,
    name="aqp.tasks.openlineage_relay_tasks.drain_openlineage_outbox",
)
def drain_openlineage_outbox(self) -> dict[str, Any]:
    """Celery beat entry point.

    Schedule via :class:`celery.schedules.crontab` or the existing
    ``CELERYBEAT_SCHEDULE`` table at ``AQP_OPENLINEAGE_RELAY_INTERVAL_SECONDS``
    (default 5 s). The function is safe to invoke ad-hoc from tests.
    """
    task_id = self.request.id or "openlineage-relay"
    return _impl(task_id)


__all__ = ["drain_openlineage_outbox"]
