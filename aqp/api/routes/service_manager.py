"""AQP service-manager API for local data-platform services."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from aqp.services import service_manager

router = APIRouter(prefix="/service-manager", tags=["service-manager"])

ServiceName = Literal["trino", "polaris", "iceberg", "superset", "airbyte", "dagster", "neo4j"]
ActionName = Literal["start", "stop", "restart"]


class ServiceActionRequest(BaseModel):
    action: ActionName


class TrinoQueryRequest(BaseModel):
    statement: str
    catalog: str | None = None
    schema_: str | None = None


@router.get("/config")
def config() -> dict[str, Any]:
    return service_manager.config_snapshot()


@router.get("/health")
def health() -> dict[str, Any]:
    return service_manager.health()


@router.get("/{name}/health")
def single_health(name: ServiceName) -> dict[str, Any]:
    return service_manager.service_health(name)


@router.get("/{name}/logs")
def logs(
    name: ServiceName,
    lines: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    return service_manager.service_logs(name, lines=lines)


@router.post("/{name}/actions")
def action(name: ServiceName, payload: ServiceActionRequest) -> dict[str, Any]:
    result = service_manager.service_action(name, payload.action)
    if not result.get("ok") and result.get("enabled") is False:
        raise HTTPException(status_code=403, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Iceberg / Polaris bootstrap
# ---------------------------------------------------------------------------


@router.get("/iceberg/status")
def iceberg_status() -> dict[str, Any]:
    return service_manager.iceberg_status()


@router.post("/iceberg/bootstrap")
def iceberg_bootstrap() -> dict[str, Any]:
    return service_manager.iceberg_bootstrap()


# ---------------------------------------------------------------------------
# Trino verification + recent queries
# ---------------------------------------------------------------------------


@router.post("/trino/verify")
def trino_verify() -> dict[str, Any]:
    return service_manager.trino_verify()


@router.get("/trino/queries")
def trino_queries(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return service_manager.trino_queries(limit=limit)


@router.post("/trino/query")
def trino_query(payload: TrinoQueryRequest) -> dict[str, Any]:
    return service_manager.trino_query(
        payload.statement, catalog=payload.catalog, schema=payload.schema_
    )

