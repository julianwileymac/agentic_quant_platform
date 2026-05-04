"""Celery tasks for refreshing :class:`StreamingDatasetLink` rows.

Walks the registry of:

- ``data_sources`` × ``streaming_dataset_links.kind == 'kafka_topic'``
  (when ``DataSource.kind`` is ``stream``).
- :class:`MarketDataProducerRow.topics` -> link to dataset table by
  naming convention (``namespace.table`` matches the topic suffix).
- :class:`PipelineManifestRow.spec_json.sink.kwargs.namespace/table`
  -> link to a dataset catalog row by namespace/table.
- :class:`AirbyteConnectionRow.namespace` -> dataset_catalog match.

The task is idempotent (the route uses ``upsert by natural key``) and
safe to run on a schedule.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from celery import shared_task

from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="aqp.tasks.streaming_link_tasks.refresh_links")
def refresh_links(self: Any) -> dict[str, Any]:
    """Refresh :class:`StreamingDatasetLink` rows from the registry."""
    task_id = getattr(self.request, "id", "local")
    emit(task_id, "start", "refreshing streaming dataset links")
    inserted = 0
    updated = 0
    try:
        from aqp.persistence import (
            DatasetCatalog,
            MarketDataProducerRow,
            StreamingDatasetLink,
        )
        from aqp.persistence.db import get_session
        from aqp.persistence.models_airbyte import AirbyteConnectionRow
        from aqp.persistence.models_dbt import DbtModelVersionRow
        from aqp.persistence.models_pipelines import PipelineManifestRow

        with get_session() as session:
            catalogs = session.query(DatasetCatalog).all()
            catalog_by_table = {
                f"{c.provider or ''}.{c.name or ''}".lower(): c
                for c in catalogs
                if c.name
            }
            catalog_by_id = {c.id: c for c in catalogs}

            def _upsert(
                *,
                dataset_id: str | None,
                kind: str,
                target_ref: str,
                direction: str = "source",
                cluster_ref: str | None = None,
                dataset_namespace: str | None = None,
                dataset_table: str | None = None,
                metadata: dict[str, Any] | None = None,
                discovered_by: str = "task:refresh_links",
            ) -> None:
                nonlocal inserted, updated
                existing = (
                    session.query(StreamingDatasetLink)
                    .filter(
                        StreamingDatasetLink.dataset_catalog_id == dataset_id,
                        StreamingDatasetLink.kind == kind,
                        StreamingDatasetLink.target_ref == target_ref,
                        StreamingDatasetLink.direction == direction,
                    )
                    .first()
                )
                if existing is None:
                    session.add(
                        StreamingDatasetLink(
                            dataset_catalog_id=dataset_id,
                            dataset_namespace=dataset_namespace,
                            dataset_table=dataset_table,
                            kind=kind,
                            target_ref=target_ref,
                            cluster_ref=cluster_ref,
                            direction=direction,
                            metadata_json=dict(metadata or {}),
                            discovered_by=discovered_by,
                            enabled=True,
                        )
                    )
                    inserted += 1
                else:
                    existing.metadata_json = {
                        **(existing.metadata_json or {}),
                        **dict(metadata or {}),
                    }
                    existing.cluster_ref = cluster_ref or existing.cluster_ref
                    existing.dataset_namespace = (
                        dataset_namespace or existing.dataset_namespace
                    )
                    existing.dataset_table = dataset_table or existing.dataset_table
                    existing.updated_at = datetime.utcnow()
                    updated += 1

            # Producers -> topics
            producers = session.query(MarketDataProducerRow).all()
            for prod in producers:
                for topic in prod.topics or []:
                    dataset = None
                    short = topic.split(".")[-2:] if topic.count(".") >= 2 else None
                    if short:
                        candidate = ".".join(short).lower()
                        dataset = catalog_by_table.get(candidate)
                    _upsert(
                        dataset_id=dataset.id if dataset else None,
                        kind="kafka_topic",
                        target_ref=topic,
                        direction="source",
                        cluster_ref=f"producer:{prod.name}",
                        dataset_namespace=dataset.provider if dataset else None,
                        dataset_table=dataset.name if dataset else None,
                        metadata={"producer": prod.name},
                    )
                    _upsert(
                        dataset_id=dataset.id if dataset else None,
                        kind="producer",
                        target_ref=prod.name,
                        direction="source",
                        cluster_ref=prod.deployment_namespace or "local",
                        dataset_namespace=dataset.provider if dataset else None,
                        dataset_table=dataset.name if dataset else None,
                        metadata={"topics": list(prod.topics or [])},
                    )

            # Pipeline manifests -> sink (iceberg) -> dataset catalog
            manifests = session.query(PipelineManifestRow).all()
            for m in manifests:
                spec = m.spec_json or {}
                sink = (spec.get("sink") or {}) if isinstance(spec, dict) else {}
                kwargs = (sink.get("kwargs") or {}) if isinstance(sink, dict) else {}
                ns = kwargs.get("namespace")
                tbl = kwargs.get("table")
                if not ns or not tbl:
                    continue
                key = f"{ns}.{tbl}".lower()
                dataset = catalog_by_table.get(key)
                _upsert(
                    dataset_id=dataset.id if dataset else None,
                    kind="sink",
                    target_ref=f"{ns}.{tbl}",
                    direction="sink",
                    cluster_ref=f"manifest:{m.id}",
                    dataset_namespace=ns,
                    dataset_table=tbl,
                    metadata={"sink": str(sink.get("name") if isinstance(sink, dict) else "")},
                )

            # dbt models -> dataset by name (best-effort)
            for dbt_row in session.query(DbtModelVersionRow).all():
                if not dbt_row.unique_id:
                    continue
                tbl = (dbt_row.alias or dbt_row.name or "").lower() if hasattr(dbt_row, "alias") else None
                tbl = tbl or (dbt_row.name or "").lower()
                if not tbl:
                    continue
                dataset = next(
                    (
                        c
                        for c in catalogs
                        if (c.name or "").lower().endswith(tbl)
                    ),
                    None,
                )
                _upsert(
                    dataset_id=dataset.id if dataset else None,
                    kind="dbt_model",
                    target_ref=dbt_row.unique_id,
                    direction="sink",
                    metadata={"dbt_unique_id": dbt_row.unique_id},
                )

            # Airbyte connections -> namespace match
            for conn in session.query(AirbyteConnectionRow).all():
                if not conn.namespace:
                    continue
                _upsert(
                    dataset_id=None,
                    kind="airbyte_connection",
                    target_ref=conn.name,
                    direction="source",
                    cluster_ref=conn.namespace,
                    dataset_namespace=conn.namespace,
                    metadata={"connector_id": conn.connector_id},
                )

            session.commit()
        result = {"inserted": int(inserted), "updated": int(updated)}
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("refresh_links failed")
        emit_error(task_id, str(exc))
        raise


__all__ = ["refresh_links"]
