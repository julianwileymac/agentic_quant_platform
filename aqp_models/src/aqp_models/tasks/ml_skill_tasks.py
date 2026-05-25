"""Celery wrapper for :class:`MLSkillRuntime`.

The route layer (``POST /ml/skills/{name}/run``) dispatches here so a
multi-step skill (regime classifier -> regime-specialised predictor)
runs out-of-band and survives an API restart.

Per :file:`.cursor/rules/tasks-api.mdc`, the task is thin: it
instantiates the runtime, calls ``run``, emits progress frames.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp_models.tasks.ml_skill_tasks.run_ml_skill")
def run_ml_skill(
    self,
    name: str,
    inputs: dict[str, Any] | None = None,
    experiment_id: str | None = None,
    test_id: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"running skill {name!r}")
    try:
        from aqp_models.registry import get_skill_spec
        from aqp_models.runtime import MLSkillRuntime

        spec = get_skill_spec(name)
        runtime = MLSkillRuntime(spec)
        result = runtime.run(
            inputs=dict(inputs or {}),
            experiment_id=experiment_id,
            test_id=test_id,
        )
        payload = {"task_id": task_id, "ok": (result.status == "succeeded"), **result.to_json()}
        if result.status == "succeeded":
            emit_done(task_id, payload)
        else:
            emit_error(task_id, result.error or "skill failed")
        return payload
    except KeyError as exc:
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_ml_skill failed")
        emit_error(task_id, str(exc))
        return {"task_id": task_id, "ok": False, "error": str(exc)}
