"""Feed configuration + sync routes for Data Fabric Phase 4."""
from __future__ import annotations

import importlib
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from aqp.api.security import require_authenticated
from aqp.data.mcp.event_bus import publish_feed_event
from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource
from aqp.persistence.models_ingestion_ledger import IngestionLedgerRow
from aqp.persistence.models_instrument_catalog import CatalogFeedEdge

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["feeds"],
    dependencies=[Depends(require_authenticated)],
)


class FeedConfigurationView(BaseModel):
    id: str
    name: str
    kind: str | None = None
    source_category: str | None = None
    connection_uri: str | None = None
    loader_class_path: str | None = None
    rate_limit_params: dict[str, Any] | None = None
    execution_schedule: str | None = None
    credentials_ref: str | None = None
    credentials_configured: bool = False
    is_enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FeedConfigurationCreate(BaseModel):
    name: str
    display_name: str | None = None
    kind: str | None = None
    vendor: str | None = None
    auth_type: str = "none"
    protocol: str = "https/json"
    source_category: str | None = None
    connection_uri: str | None = None
    loader_class_path: str | None = None
    credentials_ref: str | None = None
    rate_limit_params: dict[str, Any] | None = None
    execution_schedule: str | None = None
    is_enabled: bool = True


class FeedConfigurationUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    kind: str | None = None
    vendor: str | None = None
    auth_type: str | None = None
    protocol: str | None = None
    source_category: str | None = None
    connection_uri: str | None = None
    loader_class_path: str | None = None
    credentials_ref: str | None = None
    rate_limit_params: dict[str, Any] | None = None
    execution_schedule: str | None = None
    is_enabled: bool | None = None


class FeedEdgeView(BaseModel):
    id: str
    instrument_catalog_id: str
    data_source_id: str
    provider_specific_ticker: str
    edge_metadata_params: dict[str, Any] | None = None
    is_enabled: bool = True
    content_hash: str | None = None
    schema_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FeedLedgerView(BaseModel):
    id: str
    fabric_uuid: str
    request_hash: str
    status: str
    records_extracted: int = 0
    records_persisted: int = 0
    execution_start: datetime | None = None
    execution_end: datetime | None = None
    otel_trace_id: str | None = None


class FeedSyncRequest(BaseModel):
    time_window: tuple[str, str] | None = None
    edge_ids: list[str] | None = None
    namespace: str = "aqp_bronze_feeds"
    table_name: str | None = None
    medallion_layer: str = "bronze"
    business_metadata: dict[str, Any] | None = None


def _masked_credentials_ref(raw: str | None) -> str | None:
    return "<configured>" if raw else None


def _to_view(row: DataSource) -> FeedConfigurationView:
    return FeedConfigurationView(
        id=str(row.id),
        name=str(row.name),
        kind=getattr(row, "kind", None),
        source_category=getattr(row, "kind_subtype", None),
        connection_uri=getattr(row, "base_url", None),
        loader_class_path=getattr(row, "loader_class_path", None),
        rate_limit_params=getattr(row, "rate_limit_params", None),
        execution_schedule=getattr(row, "execution_schedule", None),
        credentials_ref=_masked_credentials_ref(getattr(row, "credentials_ref", None)),
        credentials_configured=bool(getattr(row, "credentials_ref", None)),
        is_enabled=bool(getattr(row, "enabled", True)),
        created_at=getattr(row, "created_at", None),
        updated_at=getattr(row, "updated_at", None),
    )


def _validate_loader_class_path(loader_class_path: str | None) -> None:
    if loader_class_path is None:
        return
    module_path, _, attr_name = loader_class_path.rpartition(".")
    if not module_path or not attr_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"loader_class_path {loader_class_path!r} must be a dotted module path",
        )
    try:
        module = importlib.import_module(module_path)
        getattr(module, attr_name)
    except (ImportError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"loader_class_path {loader_class_path!r} does not resolve: {exc}",
        ) from exc


def _get_feed_or_404(feed_id: str, *, session: Any) -> DataSource:
    row = session.query(DataSource).filter(DataSource.id == str(feed_id)).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"feed {feed_id!r} not found",
        )
    return row


@router.get("/", response_model=list[FeedConfigurationView])
def list_feeds(
    *,
    source_category: str | None = Query(default=None),
    is_enabled: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[FeedConfigurationView]:
    with get_session() as session:
        query = session.query(DataSource)
        if source_category is not None:
            query = query.filter(DataSource.kind_subtype == source_category)
        if is_enabled is not None:
            query = query.filter(DataSource.enabled.is_(bool(is_enabled)))
        rows = (
            query.order_by(DataSource.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_to_view(row) for row in rows]


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=FeedConfigurationView,
)
def create_feed(payload: FeedConfigurationCreate) -> FeedConfigurationView:
    _validate_loader_class_path(payload.loader_class_path)
    try:
        with get_session() as session:
            row = DataSource(
                name=payload.name,
                display_name=payload.display_name or payload.name,
                kind=payload.kind or "rest_api",
                vendor=payload.vendor,
                auth_type=payload.auth_type,
                base_url=payload.connection_uri,
                protocol=payload.protocol,
                credentials_ref=payload.credentials_ref,
                enabled=payload.is_enabled,
                kind_subtype=payload.source_category,
                loader_class_path=payload.loader_class_path,
                rate_limit_params=payload.rate_limit_params,
                execution_schedule=payload.execution_schedule,
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            view = _to_view(row)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"feed create failed: {exc.orig or exc}",
        ) from exc

    publish_feed_event(
        kind="upsert",
        data_source_id=view.id,
        payload=view.model_dump(mode="json"),
    )
    return view


@router.get("/{feed_id}", response_model=FeedConfigurationView)
def get_feed(feed_id: str) -> FeedConfigurationView:
    with get_session() as session:
        row = _get_feed_or_404(feed_id, session=session)
        return _to_view(row)


@router.put("/{feed_id}", response_model=FeedConfigurationView)
def update_feed(feed_id: str, payload: FeedConfigurationUpdate) -> FeedConfigurationView:
    with get_session() as session:
        row = _get_feed_or_404(feed_id, session=session)
        if (
            payload.loader_class_path is not None
            and payload.loader_class_path != row.loader_class_path
        ):
            _validate_loader_class_path(payload.loader_class_path)

        patch = payload.model_dump(exclude_unset=True)
        if "name" in patch and patch["name"] is not None:
            row.name = str(patch["name"])
        if "display_name" in patch:
            row.display_name = patch["display_name"] or row.name
        if "kind" in patch and patch["kind"] is not None:
            row.kind = str(patch["kind"])
        if "vendor" in patch:
            row.vendor = patch["vendor"]
        if "auth_type" in patch and patch["auth_type"] is not None:
            row.auth_type = str(patch["auth_type"])
        if "protocol" in patch and patch["protocol"] is not None:
            row.protocol = str(patch["protocol"])
        if "source_category" in patch:
            row.kind_subtype = patch["source_category"]
        if "connection_uri" in patch:
            row.base_url = patch["connection_uri"]
        if "loader_class_path" in patch:
            row.loader_class_path = patch["loader_class_path"]
        if "credentials_ref" in patch:
            row.credentials_ref = patch["credentials_ref"]
        if "rate_limit_params" in patch:
            row.rate_limit_params = patch["rate_limit_params"]
        if "execution_schedule" in patch:
            row.execution_schedule = patch["execution_schedule"]
        if "is_enabled" in patch and patch["is_enabled"] is not None:
            row.enabled = bool(patch["is_enabled"])
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.flush()
        view = _to_view(row)

    publish_feed_event(
        kind="upsert",
        data_source_id=view.id,
        payload=view.model_dump(mode="json"),
    )
    return view


@router.delete(
    "/{feed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def soft_delete_feed(feed_id: str) -> Response:
    with get_session() as session:
        row = _get_feed_or_404(feed_id, session=session)
        row.enabled = False
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.flush()
        view = _to_view(row)

    publish_feed_event(
        kind="delete",
        data_source_id=view.id,
        payload=view.model_dump(mode="json"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{feed_id}/edges", response_model=list[FeedEdgeView])
def list_feed_edges(
    feed_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[FeedEdgeView]:
    with get_session() as session:
        _get_feed_or_404(feed_id, session=session)
        rows = (
            session.query(CatalogFeedEdge)
            .filter(CatalogFeedEdge.data_source_id == str(feed_id))
            .order_by(CatalogFeedEdge.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            FeedEdgeView(
                id=str(row.id),
                instrument_catalog_id=str(row.instrument_catalog_id),
                data_source_id=str(row.data_source_id),
                provider_specific_ticker=str(row.provider_specific_ticker),
                edge_metadata_params=dict(row.edge_metadata_params or {}),
                is_enabled=bool(row.is_enabled),
                content_hash=row.content_hash,
                schema_version=row.schema_version,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@router.post("/{feed_id}/sync")
def trigger_feed_sync(feed_id: str, payload: FeedSyncRequest) -> dict[str, str]:
    with get_session() as session:
        _get_feed_or_404(feed_id, session=session)

    # Keep Celery task imports out of module scope to avoid route/task cycles.
    from aqp.tasks.data_sync_tasks import sync_feed

    task = sync_feed.delay(
        feed_id=feed_id,
        time_window=payload.time_window,
        namespace=payload.namespace,
        table_name=payload.table_name or feed_id,
        medallion_layer=payload.medallion_layer,
        business_metadata=payload.business_metadata,
        edge_ids=payload.edge_ids,
    )
    publish_feed_event(
        kind="sync_triggered",
        data_source_id=str(feed_id),
        payload={"task_id": str(task.id), "feed_id": str(feed_id)},
    )
    return {"task_id": str(task.id)}


@router.get("/{feed_id}/ledger", response_model=list[FeedLedgerView])
def list_feed_ledger(
    feed_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[FeedLedgerView]:
    with get_session() as session:
        _get_feed_or_404(feed_id, session=session)
        rows = (
            session.query(IngestionLedgerRow)
            .filter(IngestionLedgerRow.data_source_id == str(feed_id))
            .order_by(IngestionLedgerRow.execution_start.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            FeedLedgerView(
                id=str(row.id),
                fabric_uuid=str(row.fabric_uuid),
                request_hash=str(row.request_hash),
                status=str(row.execution_status),
                records_extracted=int(row.records_extracted or 0),
                records_persisted=int(row.records_persisted or 0),
                execution_start=row.execution_start,
                execution_end=row.execution_end,
                otel_trace_id=row.otel_trace_id,
            )
            for row in rows
        ]


__all__ = [
    "FeedConfigurationCreate",
    "FeedConfigurationUpdate",
    "FeedConfigurationView",
    "FeedSyncRequest",
    "router",
]
