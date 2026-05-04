"""Airbyte control-plane API for the AQP data fabric."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.config import settings
from aqp.data.airbyte import (
    AirbyteConnectionSpec,
    AirbyteConnectorDefinition,
    AirbyteDiscoverRequest,
    AirbyteEmbeddedReadRequest,
    AirbyteSyncRequest,
    ConnectorKind,
    ConnectorRuntime,
    connector_summary,
    get_connector,
    list_connectors,
    stream_entity_mappings,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_airbyte import (
    AirbyteConnectionRow,
    AirbyteSyncRunRow,
)
from aqp.services.airbyte_client import AirbyteClient, AirbyteClientError

router = APIRouter(prefix="/airbyte", tags=["airbyte"])


def _airbyte_config_snapshot() -> dict[str, Any]:
    return {
        "enabled": bool(settings.airbyte_enabled),
        "base_url": settings.airbyte_base_url,
        "api_url": settings.airbyte_api_url or settings.airbyte_base_url,
        "workspace_id_configured": bool((settings.airbyte_workspace_id or "").strip()),
        "auth_token_configured": bool((settings.airbyte_auth_token or "").strip()),
    }


class ConnectionSummary(BaseModel):
    id: str
    name: str
    source_connector_id: str
    destination_connector_id: str
    namespace: str
    airbyte_connection_id: str | None = None
    enabled: bool = True
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None


class SyncRunSummary(BaseModel):
    id: str
    connection_id: str | None = None
    task_id: str | None = None
    airbyte_job_id: str | None = None
    airbyte_connection_id: str | None = None
    runtime: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    records_synced: int = 0
    bytes_synced: int = 0
    error: str | None = None


class EmbeddedCheckRequest(BaseModel):
    connector_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class MetadataSyncRequest(BaseModel):
    discover_schemas: bool = True
    enrich_with_llm: bool = False


@router.get("/health")
def health() -> dict[str, Any]:
    cfg = _airbyte_config_snapshot()
    if not settings.airbyte_enabled:
        return {
            "ok": False,
            "airbyte": {"reachable": False, "detail": "AQP_AIRBYTE_ENABLED is false"},
            **cfg,
        }
    try:
        remote = AirbyteClient().health()
    except AirbyteClientError as exc:
        return {
            "ok": False,
            "airbyte": {"reachable": False, "detail": str(exc)},
            **cfg,
        }
    available = remote.get("available")
    if isinstance(available, bool):
        ok = available
    else:
        ok = not remote.get("error") and remote.get("ok") is not False
    return {"ok": ok, "airbyte": remote, **cfg}


@router.get("/connectors/summary")
def connectors_summary() -> dict[str, Any]:
    return connector_summary()


@router.get("/connectors", response_model=list[AirbyteConnectorDefinition])
def connectors(
    kind: ConnectorKind | None = Query(default=None),
    tag: str | None = Query(default=None),
) -> list[AirbyteConnectorDefinition]:
    return list_connectors(kind=kind, tag=tag)


@router.get("/connectors/{connector_id}", response_model=AirbyteConnectorDefinition)
def connector(connector_id: str) -> AirbyteConnectorDefinition:
    try:
        return get_connector(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="connector not found") from exc


@router.get("/connectors/{connector_id}/entity-mappings")
def connector_entity_mappings(connector_id: str) -> dict[str, Any]:
    try:
        return {"connector_id": connector_id, "mappings": stream_entity_mappings(connector_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="connector not found") from exc


@router.post("/embedded/check")
def embedded_check(req: EmbeddedCheckRequest) -> dict[str, Any]:
    from aqp.data.airbyte.embedded import EmbeddedAirbyteRunner

    try:
        return EmbeddedAirbyteRunner().check(req.connector_id, req.config, dry_run=req.dry_run)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="connector not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/discover", response_model=TaskAccepted)
def discover(req: AirbyteDiscoverRequest) -> TaskAccepted:
    from aqp.tasks.airbyte_tasks import discover_airbyte_source

    payload = req.model_dump(mode="json")
    payload["dry_run"] = req.runtime != ConnectorRuntime.FULL_AIRBYTE
    async_result = discover_airbyte_source.delay(payload)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/metadata/remote")
def remote_metadata() -> dict[str, Any]:
    """Read Airbyte control-plane metadata without starting sync jobs."""
    if not settings.airbyte_enabled:
        raise HTTPException(
            status_code=503,
            detail="Airbyte is disabled (set AQP_AIRBYTE_ENABLED=true and configure URLs / workspace / token)",
        )
    client = AirbyteClient()
    return {
        "health": client.health(),
        "workspaces": client.list_workspaces(),
        "sources": client.list_sources(),
        "destinations": client.list_destinations(),
        "connections": client.list_connections(),
        "metadata_only": True,
    }


@router.post("/metadata/sync", response_model=TaskAccepted)
def sync_metadata(req: MetadataSyncRequest) -> TaskAccepted:
    """Queue Airbyte metadata sync only; never triggers connection sync."""
    from aqp.tasks.data_metadata_tasks import sync_data_metadata

    async_result = sync_data_metadata.delay(
        {
            "targets": ["airbyte"],
            "discover_airbyte_schemas": req.discover_schemas,
            "enrich_with_llm": req.enrich_with_llm,
        }
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/embedded/read", response_model=TaskAccepted)
def embedded_read(req: AirbyteEmbeddedReadRequest) -> TaskAccepted:
    from aqp.tasks.airbyte_tasks import run_embedded_airbyte_read

    async_result = run_embedded_airbyte_read.delay(req.model_dump(mode="json"))
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/connections", response_model=list[ConnectionSummary])
def list_connections(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(
            select(AirbyteConnectionRow).order_by(AirbyteConnectionRow.name).limit(limit)
        ).scalars().all()
        return [_connection_summary(row) for row in rows]


@router.post("/connections", response_model=ConnectionSummary)
def create_connection(spec: AirbyteConnectionSpec) -> dict[str, Any]:
    with get_session() as session:
        row = AirbyteConnectionRow(
            name=spec.name,
            source_connector_id=spec.source.connector_id,
            destination_connector_id=spec.destination.connector_id,
            airbyte_source_id=spec.source.airbyte_source_id,
            airbyte_destination_id=spec.destination.airbyte_destination_id,
            airbyte_connection_id=spec.airbyte_connection_id,
            namespace=spec.namespace,
            source_config=spec.source.config,
            destination_config=spec.destination.config,
            catalog=spec.catalog,
            streams=[stream.model_dump(mode="json") for stream in spec.streams],
            entity_mappings=spec.entity_mappings,
            materialization_manifest=spec.materialization_manifest,
            schedule=spec.schedule,
            compute_backend=spec.compute_backend,
            enabled=spec.enabled,
        )
        session.add(row)
        session.flush()
        return _connection_summary(row)


@router.get("/connections/{connection_id}", response_model=AirbyteConnectionSpec)
def get_connection(connection_id: str) -> AirbyteConnectionSpec:
    with get_session() as session:
        row = session.get(AirbyteConnectionRow, connection_id)
        if row is None:
            raise HTTPException(status_code=404, detail="connection not found")
        return _connection_spec(row)


@router.post("/sync", response_model=TaskAccepted)
def sync(req: AirbyteSyncRequest) -> TaskAccepted:
    from aqp.tasks.airbyte_tasks import sync_airbyte_connection

    async_result = sync_airbyte_connection.delay(req.model_dump(mode="json"))
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/runs", response_model=list[SyncRunSummary])
def list_runs(
    connection_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(AirbyteSyncRunRow).order_by(desc(AirbyteSyncRunRow.started_at)).limit(limit)
        if connection_id:
            stmt = stmt.where(AirbyteSyncRunRow.connection_id == connection_id)
        if status:
            stmt = stmt.where(AirbyteSyncRunRow.status == status)
        rows = session.execute(stmt).scalars().all()
        return [_run_summary(row) for row in rows]


@router.get("/remote/connections")
def remote_connections() -> dict[str, Any]:
    if not settings.airbyte_enabled:
        raise HTTPException(
            status_code=503,
            detail="Airbyte is disabled (set AQP_AIRBYTE_ENABLED=true and configure URLs / workspace / token)",
        )
    return AirbyteClient().list_connections()


@router.post("/connectors/import")
def import_oss_connectors(
    url: str = "https://connectors.airbyte.com/files/registries/v0/oss_registry.json",
    api_token: str | None = None,
    overwrite_cache: bool = False,
) -> dict[str, Any]:
    """Fetch the Airbyte OSS connector registry and merge into the catalog.

    Imported entries are cached for the process lifetime and merged on top
    of the curated catalog (curated entries win on id collision).
    """
    try:
        from aqp.data.airbyte.registry import (
            load_airbyte_oss_registry,
            merged_catalog,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"registry unavailable: {exc}") from exc
    try:
        rows = load_airbyte_oss_registry(
            url, api_token=api_token, overwrite_cache=overwrite_cache
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"oss registry fetch failed: {exc}") from exc
    merged = merged_catalog(oss_url=url)
    return {
        "imported": len(rows),
        "merged_total": len(merged),
        "url": url,
    }


def _connection_summary(row: AirbyteConnectionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "source_connector_id": row.source_connector_id,
        "destination_connector_id": row.destination_connector_id,
        "namespace": row.namespace,
        "airbyte_connection_id": row.airbyte_connection_id,
        "enabled": row.enabled,
        "last_sync_status": row.last_sync_status,
        "last_sync_at": row.last_sync_at,
    }


def _connection_spec(row: AirbyteConnectionRow) -> AirbyteConnectionSpec:
    return AirbyteConnectionSpec(
        id=row.id,
        name=row.name,
        source={
            "connector_id": row.source_connector_id,
            "config": row.source_config or {},
            "airbyte_source_id": row.airbyte_source_id,
        },
        destination={
            "connector_id": row.destination_connector_id,
            "config": row.destination_config or {},
            "airbyte_destination_id": row.airbyte_destination_id,
        },
        streams=row.streams or [],
        namespace=row.namespace,
        schedule=row.schedule or {},
        catalog=row.catalog or {},
        entity_mappings=row.entity_mappings or [],
        materialization_manifest=row.materialization_manifest,
        compute_backend=row.compute_backend or "auto",
        airbyte_connection_id=row.airbyte_connection_id,
        enabled=bool(row.enabled),
    )


def _run_summary(row: AirbyteSyncRunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "task_id": row.task_id,
        "airbyte_job_id": row.airbyte_job_id,
        "airbyte_connection_id": row.airbyte_connection_id,
        "runtime": row.runtime,
        "status": row.status,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "records_synced": row.records_synced,
        "bytes_synced": row.bytes_synced,
        "error": row.error,
    }
