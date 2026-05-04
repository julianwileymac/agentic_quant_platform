"""Celery tasks for visualization asset provisioning."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app
from aqp.visualization.superset_sync import sync_superset_assets

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.visualization_tasks.sync_superset_assets")
def sync_superset_assets_task(self) -> dict[str, Any]:
    """Synchronize Trino-backed AQP datasets into Superset."""

    task_id = self.request.id or "superset-sync"
    emit(task_id, "start", "Planning Superset assets for AQP datasets")
    try:
        emit(
            task_id,
            "provisioning",
            "Creating or updating Superset database, datasets, charts, and dashboards",
        )
        result = sync_superset_assets()
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("sync_superset_assets failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.visualization_tasks.export_superset_bundle")
def export_superset_bundle_task(
    self,
    dashboard_ids: list[int] | None = None,
    label: str = "aqp",
) -> dict[str, Any]:
    """Pull a fresh CLI-compatible Superset asset zip and persist it under
    ``data/visualizations/bundles/{label}-{ts}.zip``.
    """

    from aqp.services.superset_client import SupersetClient
    from aqp.visualization.superset_bundle import export_bundle

    task_id = self.request.id or "superset-bundle-export"
    emit(task_id, "start", f"Exporting Superset bundle (label={label})")
    try:
        with SupersetClient() as client:
            zip_bytes = export_bundle(client, dashboard_ids=dashboard_ids)
        bundle_dir = Path(settings.visualization_bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        target = bundle_dir / f"{label}-{int(time.time())}.zip"
        target.write_bytes(zip_bytes)
        result = {"path": str(target), "bytes": len(zip_bytes), "dashboard_ids": dashboard_ids}
        emit(task_id, "wrote", f"Bundle written to {target}")
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("export_superset_bundle failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.visualization_tasks.import_superset_bundle")
def import_superset_bundle_task(
    self,
    bundle_path: str,
    passwords: dict[str, str] | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Push a previously-exported zip bundle back into Superset.

    ``bundle_path`` is a path on the worker filesystem; the visualization
    REST route writes uploads to ``data/visualizations/bundles/`` first and
    then enqueues this task with that path.
    """

    from aqp.services.superset_client import SupersetClient
    from aqp.visualization.superset_bundle import import_bundle

    task_id = self.request.id or "superset-bundle-import"
    emit(task_id, "start", f"Importing Superset bundle from {bundle_path}")
    try:
        path = Path(bundle_path)
        if not path.exists():
            raise FileNotFoundError(f"bundle not found: {bundle_path}")
        zip_bytes = path.read_bytes()
        with SupersetClient() as client:
            response = import_bundle(
                client,
                zip_bytes,
                passwords=passwords,
                overwrite=overwrite,
                filename=path.name,
            )
        emit_done(task_id, {"path": bundle_path, "response": response})
        return {"path": bundle_path, "response": response}
    except Exception as exc:
        logger.exception("import_superset_bundle failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.visualization_tasks.push_superset_to_datahub")
def push_superset_to_datahub_task(self) -> dict[str, Any]:
    """Push Superset metadata (databases / datasets / charts / dashboards) into DataHub.

    Uses ``acryl-datahub[superset]`` to build an ingestion recipe and run
    it via ``Pipeline.create(recipe).run()``. Short-circuits gracefully
    when ``AQP_DATAHUB_GMS_URL`` is unset or
    ``AQP_DATAHUB_SUPERSET_SYNC_ENABLED`` is false so this task is safe
    to schedule even on dev hosts where DataHub isn't running.
    """

    task_id = self.request.id or "superset-datahub-push"
    emit(task_id, "start", "Push Superset metadata into DataHub")
    try:
        if not settings.datahub_superset_sync_enabled:
            result = {"skipped": True, "reason": "AQP_DATAHUB_SUPERSET_SYNC_ENABLED=false"}
            emit_done(task_id, result)
            return result
        gms_url = (settings.datahub_gms_url or "").strip()
        if not gms_url:
            result = {"skipped": True, "reason": "AQP_DATAHUB_GMS_URL not set"}
            emit_done(task_id, result)
            return result

        try:
            from datahub.ingestion.run.pipeline import Pipeline
        except ImportError as exc:
            raise RuntimeError(
                "acryl-datahub is missing — install agentic-quant-platform[datahub-sync] "
                "or pip install 'acryl-datahub[superset,datahub-rest]>=0.13'"
            ) from exc

        recipe: dict[str, Any] = {
            "source": {
                "type": "superset",
                "config": {
                    "connect_uri": settings.superset_base_url,
                    "username": settings.superset_username,
                    "password": settings.superset_password,
                    "provider": settings.superset_provider,
                    "platform_instance": settings.datahub_platform_instance or "agentic-quant-platform",
                    "env": settings.datahub_env,
                },
            },
            "sink": {
                "type": "datahub-rest",
                "config": {
                    "server": gms_url,
                    **(
                        {"token": settings.datahub_token}
                        if settings.datahub_token
                        else {}
                    ),
                },
            },
        }
        emit(task_id, "ingesting", f"Running DataHub Superset ingestion against {gms_url}")
        pipeline = Pipeline.create(recipe)
        pipeline.run()
        pipeline.raise_from_status()
        report = pipeline.source.get_report().as_obj() if hasattr(pipeline, "source") else {}
        result = {"server": gms_url, "report": report}
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("push_superset_to_datahub failed")
        emit_error(task_id, str(exc))
        raise
