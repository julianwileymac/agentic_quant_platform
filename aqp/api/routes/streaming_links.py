"""``/datasets/{id}/streaming-links`` REST surface.

CRUD over the ``streaming_dataset_links`` table — the many-to-many
graph between dataset catalogs and Kafka topics, Flink jobs, dbt
models, Airbyte connections, Dagster assets, producers, and sinks.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.persistence import StreamingDatasetLink
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


class StreamingLinkView(BaseModel):
    id: str
    dataset_catalog_id: str | None = None
    dataset_namespace: str | None = None
    dataset_table: str | None = None
    kind: str
    target_ref: str
    cluster_ref: str | None = None
    direction: str = "source"
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    discovered_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class StreamingLinkCreate(BaseModel):
    kind: str
    target_ref: str
    direction: str = "source"
    cluster_ref: str | None = None
    dataset_namespace: str | None = None
    dataset_table: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    discovered_by: str = "user"


def _to_view(row: StreamingDatasetLink) -> StreamingLinkView:
    return StreamingLinkView(
        id=row.id,
        dataset_catalog_id=row.dataset_catalog_id,
        dataset_namespace=row.dataset_namespace,
        dataset_table=row.dataset_table,
        kind=row.kind,
        target_ref=row.target_ref,
        cluster_ref=row.cluster_ref,
        direction=row.direction,
        metadata=dict(row.metadata_json or {}),
        enabled=bool(row.enabled),
        discovered_by=row.discovered_by,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.get("/datasets/{dataset_id}/streaming-links", response_model=list[StreamingLinkView])
def list_links(dataset_id: str) -> list[StreamingLinkView]:
    with get_session() as session:
        rows = (
            session.query(StreamingDatasetLink)
            .filter(StreamingDatasetLink.dataset_catalog_id == dataset_id)
            .order_by(StreamingDatasetLink.kind.asc(), StreamingDatasetLink.target_ref.asc())
            .all()
        )
        return [_to_view(r) for r in rows]


@router.post("/datasets/{dataset_id}/streaming-links", response_model=StreamingLinkView, status_code=201)
def create_link(dataset_id: str, body: StreamingLinkCreate) -> StreamingLinkView:
    with get_session() as session:
        existing = (
            session.query(StreamingDatasetLink)
            .filter(
                StreamingDatasetLink.dataset_catalog_id == dataset_id,
                StreamingDatasetLink.kind == body.kind,
                StreamingDatasetLink.target_ref == body.target_ref,
                StreamingDatasetLink.direction == body.direction,
            )
            .first()
        )
        if existing is not None:
            existing.metadata_json = dict(body.metadata or {})
            existing.cluster_ref = body.cluster_ref
            existing.dataset_namespace = body.dataset_namespace
            existing.dataset_table = body.dataset_table
            existing.discovered_by = body.discovered_by
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            session.commit()
            return _to_view(existing)
        row = StreamingDatasetLink(
            dataset_catalog_id=dataset_id,
            dataset_namespace=body.dataset_namespace,
            dataset_table=body.dataset_table,
            kind=body.kind,
            target_ref=body.target_ref,
            cluster_ref=body.cluster_ref,
            direction=body.direction,
            metadata_json=dict(body.metadata or {}),
            discovered_by=body.discovered_by,
            enabled=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_view(row)


@router.delete(
    "/datasets/{dataset_id}/streaming-links/{link_id}",
    status_code=204,
    response_class=Response,
)
def delete_link(dataset_id: str, link_id: str) -> Response:
    with get_session() as session:
        row = session.get(StreamingDatasetLink, link_id)
        if row is None or row.dataset_catalog_id != dataset_id:
            raise HTTPException(status_code=404, detail="link not found")
        session.delete(row)
        session.commit()
    return Response(status_code=204)


@router.get("/streaming/links")
def search_streaming_links(
    kind: str | None = None,
    target_ref: str | None = None,
    direction: str | None = None,
    limit: int = 200,
) -> list[StreamingLinkView]:
    """Cross-cutting search used by the producer / topic / job detail pages."""
    with get_session() as session:
        query = session.query(StreamingDatasetLink)
        if kind:
            query = query.filter(StreamingDatasetLink.kind == kind)
        if target_ref:
            query = query.filter(StreamingDatasetLink.target_ref == target_ref)
        if direction:
            query = query.filter(StreamingDatasetLink.direction == direction)
        rows = query.order_by(StreamingDatasetLink.kind.asc()).limit(limit).all()
        return [_to_view(r) for r in rows]


@router.post("/streaming/links/refresh")
def refresh_links_async() -> dict[str, Any]:
    """Queue a background refresh that infers links from the registry."""
    try:
        from aqp.tasks.streaming_link_tasks import refresh_links

        result = refresh_links.delay()
        return {"task_id": str(getattr(result, "id", "local"))}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"refresh failed: {exc}") from exc


__all__ = ["router"]
