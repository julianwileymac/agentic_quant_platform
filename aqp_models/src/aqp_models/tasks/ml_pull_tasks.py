"""Async pull tasks for the external registry adapters.

One task per external registry kind so the Celery queue routing
(``aqp.tasks.ml_pull_tasks.*`` -> ``ml`` queue) stays uniform with the
existing ML task surface.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp_models.tasks.ml_pull_tasks.pull_model")
def pull_model(
    self,
    source: str,
    model_name: str,
    revision: str | None = None,
    include_examples: bool = False,
) -> dict[str, Any]:
    """Pull a model from the external registry identified by ``source``.

    ``source`` is the adapter kind (``"huggingface"`` / ``"torchhub"``).
    The task emits one ``start`` / ``progress`` / ``done`` /
    ``error`` frame per :file:`.cursor/rules/tasks-api.mdc`.
    """
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Pulling {model_name!r} via {source!r}")

    try:
        from aqp_models.adapters import get_adapter

        adapter = get_adapter(source)
        emit(task_id, "progress", "Adapter resolved; downloading")
        result = adapter.pull(
            model_name,
            revision=revision,
            include_examples=bool(include_examples),
        )
        if not result.ok:
            err = result.error or "pull failed"
            emit_error(task_id, err)
            return {"task_id": task_id, "ok": False, "error": err}

        payload = {
            "task_id": task_id,
            "ok": True,
            **result.to_json(),
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("pull_model failed")
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}
