"""Celery task driving the interactive Dagster sandbox.

Streams ``SandboxEvent`` records through
:func:`aqp.tasks._progress.emit` so the existing
``useChatStream`` hook in the frontend renders them without any
new transport. The frame shape (`task_id`, `stage`, `message`,
`timestamp`, `**extras`) is unchanged from AGENTS rule 4.
"""
from __future__ import annotations

import logging

from aqp.dagster.sandbox import SandboxRuntime
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.dagster_sandbox_tasks.execute_sandbox_session")
def execute_sandbox_session(self, session_id: str) -> dict:
    """Stream a sandbox execution back through the progress bus."""
    task_id = self.request.id or session_id
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        emit_error(task_id, f"sandbox session {session_id!r} not found")
        return {"ok": False, "error": "session not found"}
    emit(task_id, "start", f"sandbox session {session_id} executing")
    last_event: dict = {}
    try:
        for event in runtime.stream_execute():
            payload = event.to_json()
            last_event = payload
            emit(
                task_id,
                str(payload.get("stage") or "event"),
                str(payload.get("message") or ""),
                session_id=session_id,
                asset_key=payload.get("asset_key") or [],
                metadata=payload.get("metadata") or {},
            )
        result = {
            "ok": True,
            "session_id": session_id,
            "asset_count": len(runtime.session.asset_keys),
            "last_event": last_event,
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:
        emit_error(task_id, str(exc))
        raise
