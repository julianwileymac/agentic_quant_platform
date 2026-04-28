"""DataHub bidirectional sync endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.config import settings
from aqp.data.datahub import (
    get_client,
    iceberg_dataset_urn,
    parse_urn,
    pull_external,
    pull_platform,
    push_all,
    push_dataset,
    sync_all,
    vt_symbol_urn,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_pipelines import DatahubSyncLog

router = APIRouter(prefix="/datahub", tags=["datahub"])


class PushRequest(BaseModel):
    catalog_id: str | None = None
    urn: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class MappingResolveRequest(BaseModel):
    iceberg_identifier: str | None = None
    vt_symbol: str | None = None
    urn: str | None = None


@router.get("/status")
def status() -> dict[str, Any]:
    client = get_client()
    return {
        "configured": client.is_configured(),
        "gms_url": client.gms_url,
        "env": client.env,
        "platform": settings.datahub_platform,
        "platform_instance": settings.datahub_platform_instance,
        "sync_enabled": bool(settings.datahub_sync_enabled),
        "sync_direction": settings.datahub_sync_direction,
        "external_platforms": settings.datahub_external_platform_list,
        "ping": client.ping(),
    }


@router.post("/sync")
def trigger_sync(direction: str | None = Query(default=None)) -> dict[str, Any]:
    if direction:
        # Override via query param without mutating settings.
        from aqp.data.datahub.emitter import push_all as push
        from aqp.data.datahub.puller import pull_external as pull

        if direction == "push":
            return {"direction": "push", "push": push()}
        if direction == "pull":
            return {"direction": "pull", "pull": pull()}
        if direction == "bidirectional":
            return {
                "direction": "bidirectional",
                "push": push(),
                "pull": pull(),
            }
    return sync_all()


@router.post("/push")
def push_one(payload: PushRequest) -> dict[str, Any]:
    return push_dataset(
        urn=payload.urn,
        payload=payload.payload,
        catalog_id=payload.catalog_id,
    )


@router.post("/push-all")
def push_all_route(limit: int = Query(default=1000, ge=1, le=10000)) -> dict[str, Any]:
    return push_all(limit=limit)


@router.post("/pull")
def pull_route(platform: str | None = Query(default=None)) -> dict[str, Any]:
    if platform:
        return pull_platform(platform)
    return pull_external()


@router.get("/external")
def list_external(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    """Return the latest pull-side log entries (proxies the external catalog)."""
    with get_session() as session:
        rows = (
            session.execute(
                select(DatahubSyncLog)
                .where(DatahubSyncLog.direction == "pull")
                .order_by(desc(DatahubSyncLog.started_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        platforms: dict[str, dict[str, Any]] = {}
        for row in rows:
            urns = (row.payload or {}).get("urns") or []
            platforms.setdefault(
                row.platform or row.target,
                {
                    "platform": row.platform or row.target,
                    "platform_instance": row.platform_instance,
                    "urns": [],
                    "last_pulled_at": (row.started_at or datetime.utcnow()).isoformat(),
                },
            )
            platforms[row.platform or row.target]["urns"].extend(urns[:200])
        return {"platforms": list(platforms.values())}


@router.get("/log")
def list_log(
    direction: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(DatahubSyncLog).order_by(desc(DatahubSyncLog.started_at)).limit(limit)
        if direction:
            stmt = stmt.where(DatahubSyncLog.direction == direction)
        if status:
            stmt = stmt.where(DatahubSyncLog.status == status)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": row.id,
                "direction": row.direction,
                "target": row.target,
                "urn": row.urn,
                "platform": row.platform,
                "platform_instance": row.platform_instance,
                "status": row.status,
                "started_at": (row.started_at or datetime.utcnow()).isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "error": row.error,
            }
            for row in rows
        ]


@router.post("/mappings/resolve")
def resolve_mapping(payload: MappingResolveRequest) -> dict[str, Any]:
    """Round-trip an identifier <-> URN mapping for the UI mapper."""
    if payload.urn:
        return parse_urn(payload.urn)
    if payload.iceberg_identifier:
        urn = iceberg_dataset_urn(payload.iceberg_identifier)
        return {"input": payload.iceberg_identifier, "urn": urn, **parse_urn(urn)}
    if payload.vt_symbol:
        urn = vt_symbol_urn(payload.vt_symbol)
        return {"input": payload.vt_symbol, "urn": urn, **parse_urn(urn)}
    return {"error": "provide urn, iceberg_identifier, or vt_symbol"}


@router.get("/mappings/lookup")
def lookup_urn(urn: str = Query(...)) -> dict[str, Any]:
    return parse_urn(urn)
