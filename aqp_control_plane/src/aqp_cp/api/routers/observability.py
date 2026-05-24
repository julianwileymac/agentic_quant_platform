"""``/manage/observability/*`` — admin routes for the observability stack.

Phase 3 of the AQP infra-expansion plan. Read-only proxies to:

- Prometheus (``/api/v1/query``, ``/api/v1/query_range``, ``/api/v1/alerts``)
- Grafana (``/api/search`` for dashboards, ``/api/datasources``)
- Phoenix (``/v1/projects``)
- OTel gateway (Collector own metrics + status)

Aimed at the frontend admin pages (``aqp_client/src/routes/admin/observability/``).
The MCP-tool surface inside ``aqp/`` (``data.observability.*``) provides
the agent-facing equivalent; both call the same in-cluster URLs
resolved through the topology service.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["observability"], prefix="/observability")


def _service_endpoint(service_id: str, endpoint: str) -> str:
    url = topology_service.resolve_endpoint(service_id, endpoint)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "endpoint_unavailable",
                "service_id": service_id,
                "endpoint": endpoint,
            },
        )
    return url.rstrip("/")


# ---------------- Prometheus -----------------------------------------------


@router.get(
    "/prometheus/query",
    summary="Run an instant PromQL query.",
    response_model=ResponseEnvelope[Any],
)
async def prometheus_query(
    query: str,
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[Any]:
    base = _service_endpoint("prometheus", "query")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/api/v1/query", params={"query": query})
    return ResponseEnvelope(status="ok", data=resp.json())


@router.get(
    "/prometheus/alerts",
    summary="List active Prometheus alerts.",
    response_model=ResponseEnvelope[Any],
)
async def prometheus_alerts(
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[Any]:
    base = _service_endpoint("prometheus", "query")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/api/v1/alerts")
    return ResponseEnvelope(status="ok", data=resp.json())


# ---------------- Grafana --------------------------------------------------


@router.get(
    "/grafana/dashboards",
    summary="List Grafana dashboards.",
    response_model=ResponseEnvelope[Any],
)
async def grafana_dashboards(
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[Any]:
    base = _service_endpoint("grafana", "ui")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/api/search", params={"type": "dash-db"})
    return ResponseEnvelope(status="ok", data=resp.json())


@router.get(
    "/grafana/datasources",
    summary="List provisioned Grafana datasources.",
    response_model=ResponseEnvelope[Any],
)
async def grafana_datasources(
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[Any]:
    base = _service_endpoint("grafana", "ui")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/api/datasources")
    return ResponseEnvelope(status="ok", data=resp.json())


# ---------------- Phoenix --------------------------------------------------


@router.get(
    "/phoenix/projects",
    summary="List Arize Phoenix projects.",
    response_model=ResponseEnvelope[Any],
)
async def phoenix_projects(
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[Any]:
    base = _service_endpoint("phoenix", "ui")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base}/v1/projects")
    return ResponseEnvelope(status="ok", data=resp.json() if resp.text else [])


# ---------------- OTel collector -------------------------------------------


@router.get(
    "/otel/health",
    summary="OpenTelemetry Collector gateway health.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def otel_health(
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[dict[str, Any]]:
    snapshot = await topology_service.probe_service_health("otel-collector")
    return ResponseEnvelope(status="ok", data=snapshot)


__all__ = ["router"]
