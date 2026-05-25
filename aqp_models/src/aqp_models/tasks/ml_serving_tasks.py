"""Continuous-batching serving lifecycle tasks.

The route layer mainly drives :class:`ServeHandler` synchronously, but
exposes a Celery wrapper so kill-switch fan-out / scheduled session
warm-up / bulk halts can run out-of-band without holding the API
process.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp_models.tasks.ml_serving_tasks.halt_all_sessions")
def halt_all_sessions(self) -> dict[str, Any]:
    """Halt every serving session this worker process knows about."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", "halting active serving sessions")
    try:
        from aqp_models.handlers import ServeHandler

        n = ServeHandler.halt_all()
        payload = {"task_id": task_id, "ok": True, "halted": int(n)}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("halt_all_sessions failed")
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}


@celery_app.task(bind=True, name="aqp_models.tasks.ml_serving_tasks.list_sessions")
def list_sessions(self) -> dict[str, Any]:
    """Return the descriptors for every active serving session."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", "listing serving sessions")
    try:
        from aqp_models.handlers import ServeHandler

        sessions = ServeHandler.list_sessions()
        payload = {"task_id": task_id, "ok": True, "sessions": sessions, "n_sessions": len(sessions)}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_sessions failed")
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}
