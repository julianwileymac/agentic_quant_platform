"""Celery tasks for DataHub bidirectional sync."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.datahub_tasks.push_dataset")
def push_dataset_task(
    self,
    *,
    catalog_id: str | None = None,
    urn: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = str(self.request.id or "datahub_push")
    try:
        from aqp.data.datahub.emitter import push_dataset

        emit(task_id, "push", f"urn={urn or catalog_id}")
        result = push_dataset(catalog_id=catalog_id, urn=urn, payload=payload)
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("push_dataset_task failed")
        emit_error(task_id, f"push_dataset_failed: {exc}")
        return {"emitted": False, "error": str(exc)}


@celery_app.task(bind=True, name="aqp.tasks.datahub_tasks.pull_external_catalog")
def pull_external_catalog_task(self) -> dict[str, Any]:
    task_id = str(self.request.id or "datahub_pull")
    try:
        from aqp.data.datahub.puller import pull_external

        emit(task_id, "pull", "fetching external DataHub state")
        result = pull_external()
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("pull_external_catalog_task failed")
        emit_error(task_id, f"pull_external_failed: {exc}")
        return {"error": str(exc)}


@celery_app.task(bind=True, name="aqp.tasks.datahub_tasks.sync_all")
def sync_all_task(self) -> dict[str, Any]:
    task_id = str(self.request.id or "datahub_sync_all")
    try:
        from aqp.data.datahub.sync import sync_all

        emit(task_id, "sync", "starting bidirectional sync")
        result = sync_all()
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_all_task failed")
        emit_error(task_id, f"sync_all_failed: {exc}")
        return {"error": str(exc)}
