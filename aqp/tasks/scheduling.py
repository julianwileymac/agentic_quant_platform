"""Celery beat schedule synthesis from data-control rows.

Reads :class:`PipelineManifestRow.schedule_cron` and the ``cron``
entries inside :class:`DatasetPipelineConfigRow.automations` and
materialises them into a Celery beat schedule dict that can be merged
into ``celery_app.conf.beat_schedule``.

The synthesizer is invoked by:

- :func:`aqp.tasks.celery_app` lazily on first import (via
  :func:`apply_data_control_schedule`), so the beat process picks up
  any cron-driven entries on next start.
- The ``POST /data-control/schedules`` endpoint, which calls
  :func:`refresh_celery_beat_schedule` after persisting an upsert so
  in-process callers (the API + the local Celery scheduler) re-render
  the schedule without a full restart.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Celery beat name prefixes used for the synthesized entries so they are
# easy to identify (and prune) in the merged schedule.
_MANIFEST_PREFIX = "data-pipeline-manifest::"
_CONFIG_PREFIX = "data-pipeline-config::"


def _parse_cron(expression: str) -> Any | None:
    """Translate a cron string to ``celery.schedules.crontab``.

    Returns ``None`` if the expression cannot be parsed; the caller
    skips the entry rather than failing the whole synthesis.
    """
    if not expression:
        return None
    parts = str(expression).strip().split()
    if len(parts) != 5:
        logger.debug("scheduling: skipping non-5-field cron %s", expression)
        return None
    try:
        from celery.schedules import crontab
    except Exception as exc:  # pragma: no cover - celery not installed
        logger.debug("scheduling: celery unavailable: %s", exc)
        return None
    try:
        return crontab(
            minute=parts[0],
            hour=parts[1],
            day_of_month=parts[2],
            month_of_year=parts[3],
            day_of_week=parts[4],
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("scheduling: invalid cron %r: %s", expression, exc)
        return None


def synthesize_beat_schedule() -> dict[str, dict[str, Any]]:
    """Render the current data-control schedule into a beat-schedule dict."""
    out: dict[str, dict[str, Any]] = {}
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_data_control import DatasetPipelineConfigRow
        from aqp.persistence.models_pipelines import PipelineManifestRow
    except Exception as exc:  # pragma: no cover
        logger.debug("scheduling: persistence unavailable: %s", exc)
        return out

    try:
        with get_session() as session:
            manifests = (
                session.query(PipelineManifestRow)
                .filter(
                    PipelineManifestRow.enabled.is_(True),
                    PipelineManifestRow.schedule_cron.is_not(None),
                )
                .all()
            )
            for row in manifests:
                schedule = _parse_cron(row.schedule_cron or "")
                if schedule is None:
                    continue
                key = f"{_MANIFEST_PREFIX}{row.id}"
                out[key] = {
                    "task": "aqp.tasks.engine_tasks.run_pipeline_manifest",
                    "schedule": schedule,
                    "kwargs": {"manifest_id": row.id, "triggered_by": "beat"},
                    "options": {"queue": "ingestion"},
                }
            configs = (
                session.query(DatasetPipelineConfigRow)
                .filter(DatasetPipelineConfigRow.is_active.is_(True))
                .all()
            )
            for cfg in configs:
                if not cfg.automations:
                    continue
                for entry in cfg.automations:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("kind") != "cron":
                        continue
                    schedule = _parse_cron(entry.get("cron") or "")
                    if schedule is None:
                        continue
                    preset = (cfg.config_json or {}).get("preset")
                    if preset:
                        task_name = (
                            f"aqp.tasks.dataset_preset_tasks.ingest_{preset}"
                        )
                        kwargs: dict[str, Any] = {}
                    elif cfg.manifest_id:
                        task_name = "aqp.tasks.engine_tasks.run_pipeline_manifest"
                        kwargs = {"manifest_id": cfg.manifest_id, "triggered_by": "beat"}
                    else:
                        continue
                    key = f"{_CONFIG_PREFIX}{cfg.id}"
                    out[key] = {
                        "task": task_name,
                        "schedule": schedule,
                        "kwargs": kwargs,
                        "options": {"queue": "ingestion"},
                    }
    except Exception as exc:  # noqa: BLE001
        logger.debug("scheduling: synthesis failed: %s", exc)
    return out


def apply_data_control_schedule() -> dict[str, dict[str, Any]]:
    """Merge the synthesized beat schedule into ``celery_app.conf``.

    Returns the rendered dict for inspection / debugging.
    """
    rendered = synthesize_beat_schedule()
    if not rendered:
        return rendered
    try:
        from aqp.tasks.celery_app import celery_app

        existing = dict(celery_app.conf.beat_schedule or {})
        # Drop any previously-synthesized entries before re-merging.
        existing = {
            k: v
            for k, v in existing.items()
            if not k.startswith((_MANIFEST_PREFIX, _CONFIG_PREFIX))
        }
        existing.update(rendered)
        celery_app.conf.beat_schedule = existing
    except Exception as exc:  # pragma: no cover
        logger.debug("scheduling: apply failed: %s", exc)
    return rendered


def refresh_celery_beat_schedule() -> dict[str, dict[str, Any]]:
    """Public entry point used by ``POST /data-control/schedules``."""
    return apply_data_control_schedule()


__all__ = [
    "apply_data_control_schedule",
    "refresh_celery_beat_schedule",
    "synthesize_beat_schedule",
]
