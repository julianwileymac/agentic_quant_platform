"""Compilation Celery tasks driving :class:`ProductionizeHandler`.

Each task accepts a ``model_version_id`` so the worker re-fetches the
ORM row inside the task (Hard Rule 5: cross-task state through
Postgres, never pickled ORM objects). The handler reads the artifact
path / SHA-256 / format from the row, loads the model via
:class:`LoadHandler`, and routes through the matching compiler.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aqp_models.tasks.ml_productionize_tasks.productionize_model_version",
)
def productionize_model_version(
    self,
    model_version_id: str,
    target: str,
    compile_kwargs: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Compile a registered model to ONNX / TensorRT / TorchScript / quantize."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"productionize {model_version_id!r} -> {target!r}")

    try:
        from aqp_models.handlers import LoadHandler, ProductionizeHandler

        loader = LoadHandler()
        load_result = loader.invoke(model_version_id=model_version_id)
        if not load_result.ok:
            err = load_result.error or "model load failed"
            emit_error(task_id, err)
            return {"task_id": task_id, "ok": False, "error": err}
        emit(task_id, "progress", f"model loaded ({load_result.metadata.get('format')})")

        handler = ProductionizeHandler()
        result = handler.invoke(
            model=load_result.data,
            target=target,
            model_version_id=model_version_id,
            compiler_kwargs=dict(compile_kwargs or {}),
            output_path=output_path,
        )
        if not result.ok:
            emit_error(task_id, result.error or "compile failed")
            return {"task_id": task_id, "ok": False, "error": result.error}

        payload = {"task_id": task_id, "ok": True, **(result.data or {})}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("productionize_model_version failed")
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}
