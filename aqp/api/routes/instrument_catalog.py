"""Instrument catalog routes for Data Fabric Phase 4."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, or_

from aqp.api.security import require_authenticated
from aqp.persistence.db import get_session
from aqp.persistence.models_instrument_catalog import CatalogFeedEdge, InstrumentCatalog

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["instruments"],
    dependencies=[Depends(require_authenticated)],
)


class InstrumentCatalogView(BaseModel):
    id: str
    universal_ticker: str
    asset_class: str
    exchange_code: str | None = None
    metadata_blob: dict[str, Any] = Field(default_factory=dict)
    is_actively_traded: bool = True
    last_catalog_sync: datetime | None = None
    content_hash: str
    schema_version: int = 1
    promoted_instrument_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InstrumentEdgeView(BaseModel):
    id: str
    instrument_catalog_id: str
    data_source_id: str
    provider_specific_ticker: str
    edge_metadata_params: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    content_hash: str
    schema_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InstrumentCatalogSyncRequest(BaseModel):
    batch_size: int = Field(default=1000, ge=1, le=50_000)


def _to_view(row: InstrumentCatalog) -> InstrumentCatalogView:
    return InstrumentCatalogView(
        id=str(row.id),
        universal_ticker=str(row.universal_ticker),
        asset_class=str(row.asset_class),
        exchange_code=row.exchange_code,
        metadata_blob=dict(row.metadata_blob or {}),
        is_actively_traded=bool(row.is_actively_traded),
        last_catalog_sync=row.last_catalog_sync,
        content_hash=str(row.content_hash),
        schema_version=int(row.schema_version or 1),
        promoted_instrument_id=row.promoted_instrument_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=list[InstrumentCatalogView])
def list_instruments(
    *,
    asset_class: str | None = Query(default=None),
    exchange_code: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[InstrumentCatalogView]:
    with get_session() as session:
        stmt = session.query(InstrumentCatalog)
        if asset_class:
            stmt = stmt.filter(InstrumentCatalog.asset_class == asset_class)
        if exchange_code:
            stmt = stmt.filter(InstrumentCatalog.exchange_code == exchange_code)
        if query:
            needle = f"%{query.strip()}%"
            stmt = stmt.filter(
                or_(
                    InstrumentCatalog.universal_ticker.ilike(needle),
                    cast(InstrumentCatalog.metadata_blob, String).ilike(needle),
                )
            )
        rows = (
            stmt.order_by(InstrumentCatalog.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_to_view(row) for row in rows]


@router.get("/{symbol_uuid}", response_model=InstrumentCatalogView)
def get_instrument(symbol_uuid: str) -> InstrumentCatalogView:
    with get_session() as session:
        row = (
            session.query(InstrumentCatalog)
            .filter(InstrumentCatalog.id == str(symbol_uuid))
            .first()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"instrument catalog row {symbol_uuid!r} not found",
            )
        return _to_view(row)


@router.get("/{symbol_uuid}/edges", response_model=list[InstrumentEdgeView])
def list_instrument_edges(
    symbol_uuid: str,
    *,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[InstrumentEdgeView]:
    with get_session() as session:
        instrument = (
            session.query(InstrumentCatalog)
            .filter(InstrumentCatalog.id == str(symbol_uuid))
            .first()
        )
        if instrument is None:
            raise HTTPException(
                status_code=404,
                detail=f"instrument catalog row {symbol_uuid!r} not found",
            )
        rows = (
            session.query(CatalogFeedEdge)
            .filter(CatalogFeedEdge.instrument_catalog_id == str(symbol_uuid))
            .order_by(CatalogFeedEdge.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            InstrumentEdgeView(
                id=str(row.id),
                instrument_catalog_id=str(row.instrument_catalog_id),
                data_source_id=str(row.data_source_id),
                provider_specific_ticker=str(row.provider_specific_ticker),
                edge_metadata_params=dict(row.edge_metadata_params or {}),
                is_enabled=bool(row.is_enabled),
                content_hash=str(row.content_hash),
                schema_version=int(row.schema_version or 1),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@router.post("/sync")
def trigger_instrument_catalog_sync(
    payload: InstrumentCatalogSyncRequest,
) -> dict[str, str]:
    # Keep Celery imports local to route functions.
    from aqp.tasks.instrument_catalog_tasks import sync_finance_database

    task = sync_finance_database.delay(batch_size=payload.batch_size)
    return {"task_id": str(task.id)}


__all__ = [
    "InstrumentCatalogSyncRequest",
    "InstrumentCatalogView",
    "router",
]
