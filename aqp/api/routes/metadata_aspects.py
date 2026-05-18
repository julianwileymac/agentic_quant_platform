"""Read-only metadata aspect browser routes for operator UI."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func, or_, select

from aqp.api.security import require_authenticated
from aqp.auth import RequestContext, current_context
from aqp.data.mcp.tools.aspects import _walk_lineage
from aqp.metadata import parse_urn
from aqp.metadata.openmetadata.models_lineage import EntityLineage
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["metadata", "aspects"],
    dependencies=[Depends(require_authenticated)],
)


class MetadataEntitySummaryOut(BaseModel):
    urn: str
    entity_type: str
    created_at: datetime
    updated_at: datetime
    aspect_count: int


class MetadataEntityListOut(BaseModel):
    items: list[MetadataEntitySummaryOut] = Field(default_factory=list)
    total: int = 0


class MetadataAspectLatestOut(BaseModel):
    id: str
    version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    created_at: datetime
    created_by: str | None = None
    system_metadata: dict[str, Any] = Field(default_factory=dict)


class MetadataEntityDetailOut(BaseModel):
    urn: str
    entity_type: str
    created_at: datetime
    updated_at: datetime
    aspects: dict[str, MetadataAspectLatestOut] = Field(default_factory=dict)


class EntityAspectHistoryRowOut(BaseModel):
    id: str
    aspect_name: str
    version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    created_at: datetime
    created_by: str | None = None
    system_metadata: dict[str, Any] = Field(default_factory=dict)


class RecentAspectWriteOut(BaseModel):
    urn: str
    aspect_name: str
    version: int
    created_at: datetime


class MetadataAspectStatsOut(BaseModel):
    entity_count_by_type: dict[str, int] = Field(default_factory=dict)
    aspect_count_by_name: dict[str, int] = Field(default_factory=dict)
    recent_writes: list[RecentAspectWriteOut] = Field(default_factory=list)


def _workspace_scope_clause(model: Any, workspace_id: str | None) -> Any:
    workspace_col = getattr(model, "workspace_id")
    if workspace_id:
        return or_(workspace_col == workspace_id, workspace_col.is_(None))
    return workspace_col.is_(None)


def _normalise_urn(raw_urn: str) -> str:
    urn = unquote(raw_urn)
    try:
        parse_urn(urn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid urn: {exc}") from exc
    return urn


def _coerce_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _load_entity_or_404(*, session: Any, urn: str, ctx: RequestContext) -> MetadataEntity:
    row = session.execute(
        select(MetadataEntity)
        .where(MetadataEntity.urn == urn)
        .where(_workspace_scope_clause(MetadataEntity, ctx.workspace_id))
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"metadata entity {urn!r} not found")
    return row


@router.get("/entities", response_model=MetadataEntityListOut)
def list_metadata_entities(
    entity_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(current_context),
) -> MetadataEntityListOut:
    search_value = (search or "").strip() or None
    with get_session() as session:
        entity_scope = _workspace_scope_clause(MetadataEntity, ctx.workspace_id)
        aspect_scope = _workspace_scope_clause(EntityAspect, ctx.workspace_id)
        aspect_counts = (
            select(
                EntityAspect.urn.label("urn"),
                func.count(EntityAspect.id).label("aspect_count"),
            )
            .where(aspect_scope)
            .group_by(EntityAspect.urn)
            .subquery()
        )

        stmt = (
            select(
                MetadataEntity,
                func.coalesce(aspect_counts.c.aspect_count, 0).label("aspect_count"),
            )
            .outerjoin(aspect_counts, MetadataEntity.urn == aspect_counts.c.urn)
            .where(entity_scope)
        )
        total_stmt = select(func.count(MetadataEntity.urn)).where(entity_scope)
        if entity_type:
            stmt = stmt.where(MetadataEntity.entity_type == entity_type)
            total_stmt = total_stmt.where(MetadataEntity.entity_type == entity_type)
        if search_value:
            stmt = stmt.where(MetadataEntity.urn.ilike(f"%{search_value}%"))
            total_stmt = total_stmt.where(MetadataEntity.urn.ilike(f"%{search_value}%"))

        rows = session.execute(
            stmt.order_by(desc(MetadataEntity.updated_at), asc(MetadataEntity.urn))
            .limit(limit)
            .offset(offset)
        ).all()
        total = int(session.execute(total_stmt).scalar_one() or 0)

    items = [
        MetadataEntitySummaryOut(
            urn=str(entity_row.urn),
            entity_type=str(entity_row.entity_type),
            created_at=entity_row.created_at,
            updated_at=entity_row.updated_at,
            aspect_count=int(aspect_count or 0),
        )
        for entity_row, aspect_count in rows
    ]
    return MetadataEntityListOut(items=items, total=total)


@router.get("/entities/{urn:path}", response_model=MetadataEntityDetailOut)
def describe_metadata_entity(
    urn: str,
    ctx: RequestContext = Depends(current_context),
) -> MetadataEntityDetailOut:
    target_urn = _normalise_urn(urn)
    with get_session() as session:
        entity_row = _load_entity_or_404(session=session, urn=target_urn, ctx=ctx)
        aspect_rows = session.execute(
            select(EntityAspect)
            .where(EntityAspect.urn == target_urn)
            .where(_workspace_scope_clause(EntityAspect, ctx.workspace_id))
            .order_by(
                asc(EntityAspect.aspect_name),
                desc(EntityAspect.version),
                desc(EntityAspect.created_at),
            )
        ).scalars().all()

    aspects: dict[str, MetadataAspectLatestOut] = {}
    for row in aspect_rows:
        aspect_name = str(row.aspect_name)
        if aspect_name in aspects:
            continue
        aspects[aspect_name] = MetadataAspectLatestOut(
            id=str(row.id),
            version=int(row.version),
            payload=_coerce_json_dict(row.payload),
            payload_hash=str(row.payload_hash),
            created_at=row.created_at,
            created_by=row.created_by,
            system_metadata=_coerce_json_dict(row.system_metadata),
        )
    return MetadataEntityDetailOut(
        urn=str(entity_row.urn),
        entity_type=str(entity_row.entity_type),
        created_at=entity_row.created_at,
        updated_at=entity_row.updated_at,
        aspects=aspects,
    )


@router.get("/entities/{urn:path}/history", response_model=list[EntityAspectHistoryRowOut])
def metadata_entity_history(
    urn: str,
    aspect_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ctx: RequestContext = Depends(current_context),
) -> list[EntityAspectHistoryRowOut]:
    target_urn = _normalise_urn(urn)
    with get_session() as session:
        _load_entity_or_404(session=session, urn=target_urn, ctx=ctx)
        stmt = (
            select(EntityAspect)
            .where(EntityAspect.urn == target_urn)
            .where(_workspace_scope_clause(EntityAspect, ctx.workspace_id))
        )
        if aspect_name:
            stmt = stmt.where(EntityAspect.aspect_name == aspect_name)
        rows = session.execute(
            stmt.order_by(asc(EntityAspect.aspect_name), desc(EntityAspect.version)).limit(limit)
        ).scalars().all()
    return [
        EntityAspectHistoryRowOut(
            id=str(row.id),
            aspect_name=str(row.aspect_name),
            version=int(row.version),
            payload=_coerce_json_dict(row.payload),
            payload_hash=str(row.payload_hash),
            created_at=row.created_at,
            created_by=row.created_by,
            system_metadata=_coerce_json_dict(row.system_metadata),
        )
        for row in rows
    ]


@router.get("/lineage/{urn:path}", response_model=EntityLineage)
def metadata_lineage(
    urn: str,
    depth: int = Query(default=2, ge=1, le=10),
    direction: Literal["upstream", "downstream", "both"] = Query(default="both"),
    ctx: RequestContext = Depends(current_context),
) -> EntityLineage:
    target_urn = _normalise_urn(urn)
    with get_session() as session:
        _load_entity_or_404(session=session, urn=target_urn, ctx=ctx)
        payload = _walk_lineage(
            session=session,
            urn=target_urn,
            depth=depth,
            direction=direction,
            workspace_id=ctx.workspace_id,
        )
    try:
        return EntityLineage.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("metadata lineage payload validation failed")
        raise HTTPException(status_code=502, detail=f"invalid lineage payload: {exc}") from exc


@router.get("/stats", response_model=MetadataAspectStatsOut)
def metadata_aspect_stats(
    ctx: RequestContext = Depends(current_context),
) -> MetadataAspectStatsOut:
    with get_session() as session:
        entity_scope = _workspace_scope_clause(MetadataEntity, ctx.workspace_id)
        aspect_scope = _workspace_scope_clause(EntityAspect, ctx.workspace_id)
        entity_rows = session.execute(
            select(MetadataEntity.entity_type, func.count(MetadataEntity.urn))
            .where(entity_scope)
            .group_by(MetadataEntity.entity_type)
            .order_by(asc(MetadataEntity.entity_type))
        ).all()
        aspect_rows = session.execute(
            select(EntityAspect.aspect_name, func.count(EntityAspect.id))
            .where(aspect_scope)
            .group_by(EntityAspect.aspect_name)
            .order_by(asc(EntityAspect.aspect_name))
        ).all()
        recent_rows = session.execute(
            select(
                EntityAspect.urn,
                EntityAspect.aspect_name,
                EntityAspect.version,
                EntityAspect.created_at,
            )
            .where(aspect_scope)
            .order_by(desc(EntityAspect.created_at))
            .limit(20)
        ).all()
    return MetadataAspectStatsOut(
        entity_count_by_type={str(name): int(count) for name, count in entity_rows},
        aspect_count_by_name={str(name): int(count) for name, count in aspect_rows},
        recent_writes=[
            RecentAspectWriteOut(
                urn=str(urn_value),
                aspect_name=str(aspect_name),
                version=int(version),
                created_at=created_at,
            )
            for urn_value, aspect_name, version, created_at in recent_rows
        ],
    )


__all__ = [
    "EntityAspectHistoryRowOut",
    "MetadataAspectStatsOut",
    "MetadataEntityDetailOut",
    "MetadataEntityListOut",
    "MetadataEntitySummaryOut",
    "router",
]
