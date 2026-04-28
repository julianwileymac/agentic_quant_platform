"""Celery tasks for entity extraction + LLM enrichment.

Every task uses :mod:`aqp.tasks._progress` for status updates so the
WebSocket bridge keeps streaming consistent payloads.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.entity_tasks.extract_entities")
def extract_entities(
    self,
    *,
    flavor: str,
    iceberg_identifier: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    head_rows: int | None = 200_000,
    extractor_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract entities from an Iceberg table or an inline rows payload.

    ``flavor`` corresponds to a key in
    :data:`aqp.data.entities.extractors.EXTRACTOR_REGISTRY`. When
    ``iceberg_identifier`` is provided the task reads up to ``head_rows``
    rows via :func:`aqp.data.iceberg_catalog.read_arrow`. Otherwise it
    consumes ``rows`` directly.
    """
    task_id = str(self.request.id or "extract_entities")
    try:
        from aqp.data.entities.extractors import EXTRACTOR_REGISTRY

        if flavor not in EXTRACTOR_REGISTRY:
            raise ValueError(f"unknown extractor flavor {flavor!r}")
        extractor_cls = EXTRACTOR_REGISTRY[flavor]
        kwargs = dict(extractor_kwargs or {})
        if iceberg_identifier and "attach_iceberg_identifier" not in kwargs:
            kwargs["attach_iceberg_identifier"] = iceberg_identifier
        if iceberg_identifier and "source_dataset" not in kwargs:
            kwargs["source_dataset"] = iceberg_identifier

        emit(task_id, "load", f"flavor={flavor} iceberg={iceberg_identifier}")
        if iceberg_identifier and rows is None:
            from aqp.data.iceberg_catalog import read_arrow

            table = read_arrow(iceberg_identifier, limit=head_rows or 200_000)
            rows_iter = table.to_pylist()
        else:
            rows_iter = list(rows or [])

        extractor = extractor_cls(**kwargs)
        emit(task_id, "extract", f"rows={len(rows_iter)}")
        result = extractor.run(rows_iter)
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("extract_entities failed")
        emit_error(task_id, f"extract_entities_failed: {exc}")
        return {"error": str(exc)}


@celery_app.task(bind=True, name="aqp.tasks.entity_tasks.enrich_entity")
def enrich_entity(
    self,
    *,
    entity_id: str,
    enricher: str = "description",
    enricher_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a single enricher (description / relation / dedup / tagging)."""
    task_id = str(self.request.id or "enrich_entity")
    try:
        from aqp.data.entities.enrichers import ENRICHER_REGISTRY

        if enricher not in ENRICHER_REGISTRY:
            raise ValueError(f"unknown enricher {enricher!r}")
        cls = ENRICHER_REGISTRY[enricher]
        emit(task_id, "enrich", f"entity={entity_id} kind={enricher}")
        instance = cls(**(enricher_kwargs or {}))
        result = instance.run([entity_id])
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("enrich_entity failed")
        emit_error(task_id, f"enrich_entity_failed: {exc}")
        return {"error": str(exc)}


@celery_app.task(bind=True, name="aqp.tasks.entity_tasks.dedup_entities")
def dedup_entities(
    self,
    *,
    kind: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Run the dedup enricher across the most recent entities of one kind."""
    task_id = str(self.request.id or "dedup_entities")
    try:
        from aqp.data.entities.enrichers import DedupEnricher
        from aqp.data.entities.registry import list_entities

        rows = list_entities(kind=kind, limit=limit)
        emit(task_id, "dedup", f"kind={kind or '*'} count={len(rows)}")
        ids = [row["id"] for row in rows]
        enricher = DedupEnricher()
        result = enricher.run(ids)
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("dedup_entities failed")
        emit_error(task_id, f"dedup_entities_failed: {exc}")
        return {"error": str(exc)}
