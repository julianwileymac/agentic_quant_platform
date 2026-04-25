"""Celery task for LoRA / QLoRA fine-tuning jobs."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.finetune_tasks.train_finetune")
def train_finetune(self, job_dict: dict[str, Any]) -> dict[str, Any]:
    """Run one :class:`FinetuneJob` (serialized as a dict)."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "Loading LoRA/QLoRA config…")
    try:
        from aqp.ml.finetune.config import FinetuneJob
        from aqp.ml.finetune.trainer import run_finetune

        job = FinetuneJob.model_validate(job_dict)
        emit(task_id, "running", f"Fine-tuning {job.base_model} on {job.dataset}…")
        summary = run_finetune(job)
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # pragma: no cover - runtime
        logger.exception("train_finetune failed")
        emit_error(task_id, str(exc))
        raise
