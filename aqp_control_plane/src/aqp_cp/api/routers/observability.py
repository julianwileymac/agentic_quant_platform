"""``/manage/observability/*`` — admin routes for the observability stack.

Phase 3 of the AQP infra-expansion plan + Phase 1.3 of the control-plane
maturation. Read-only proxies to:

- Prometheus (``/api/v1/query``, ``/api/v1/query_range``, ``/api/v1/alerts``)
- Grafana (``/api/search`` for dashboards, ``/api/datasources``)
- Phoenix (``/v1/projects``)
- OTel gateway (Collector own metrics + status)

Aimed at the frontend admin pages (``aqp_client/src/routes/admin/observability/``
and ``aqp_admin/aqp_admin_ui/src/routes/tenants/$orgId.tsx``). The
MCP-tool surface inside ``aqp/`` (``data.observability.*``) provides
the agent-facing equivalent; both call the same in-cluster URLs
resolved through the topology service.

Phase 1.3 adds an *identity-aware* PromQL proxy that injects the
caller's ``aqp_tenant="<org_id>"`` label into every selector before
the request hits Prometheus. ``admin:cluster`` operators may opt out
explicitly. A denylist suppresses cross-tenant infra metrics
(``up``, ``kube_node_*``, ``prometheus_*``).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from aqp_platform_core.auth import SCOPE_ADMIN_CLUSTER

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service
from aqp_cp.services.prometheus import (
    IdentityAwarePrometheusClient,
    PromQLDeniedError,
    PromQLLabelInjector,
)
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"], prefix="/observability")

_PROM_CLIENT: IdentityAwarePrometheusClient | None = None


def _prometheus_client() -> IdentityAwarePrometheusClient:
    global _PROM_CLIENT
    settings = get_settings()
    if _PROM_CLIENT is None or _PROM_CLIENT.base_url != settings.prometheus_url.rstrip("/"):
        _PROM_CLIENT = IdentityAwarePrometheusClient(
            base_url=settings.prometheus_url,
            injector=PromQLLabelInjector(
                tenant_label=settings.prometheus_tenant_label,
                deny_patterns=tuple(settings.prometheus_deny_metrics),
            ),
        )
    return _PROM_CLIENT


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


# ---------------- Identity-aware PromQL proxy ------------------------------


@router.post(
    "/prometheus/query/tenant",
    summary="Tenant-scoped PromQL instant query (identity-aware proxy).",
    description=(
        "Rewrites every metric selector in ``expression`` to include "
        "``{aqp_tenant=\"<org_id>\"}`` (label name configurable via "
        "``AQP_CP_PROMETHEUS_TENANT_LABEL``) before forwarding to "
        "Prometheus. ``admin:cluster`` operators may opt out by "
        "passing ``disable_tenant_filter=true``. Deny-listed metrics "
        "return HTTP 403 with the metric names listed for audit. "
        "Required scope: ``read:observability``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def prometheus_query_tenant(
    expression: str = Query(..., alias="query"),
    time: float | None = None,
    disable_tenant_filter: bool = False,
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[dict[str, Any]]:
    if disable_tenant_filter and not user.has_scope(SCOPE_ADMIN_CLUSTER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "error_description": (
                    "disable_tenant_filter requires admin:cluster"
                ),
            },
        )
    tenant_id = user.org_id or ""
    if not tenant_id and not disable_tenant_filter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "missing_tenant_claim",
                "error_description": (
                    "the JWT must carry an https://aqp.internal/org_id "
                    "claim for identity-aware Prometheus access"
                ),
            },
        )
    client = _prometheus_client()
    try:
        result = await client.query(
            expression=expression,
            tenant_id=tenant_id,
            time=time,
            disable_tenant_filter=disable_tenant_filter,
        )
    except PromQLDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "metric_denied",
                "error_description": (
                    "query references deny-listed metric(s); these are "
                    "never returned cross-tenant"
                ),
                "metrics": list(exc.metrics),
            },
        ) from exc
    return ResponseEnvelope(
        status="ok",
        data={
            "rewritten_query": result.rewritten_query,
            "metrics_seen": list(result.metrics_seen),
            "tenant_id": tenant_id,
            "disable_tenant_filter": disable_tenant_filter,
            "data": result.data,
        },
    )


@router.post(
    "/prometheus/query_range/tenant",
    summary="Tenant-scoped PromQL range query (identity-aware proxy).",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def prometheus_query_range_tenant(
    expression: str = Query(..., alias="query"),
    start: float = Query(...),
    end: float = Query(...),
    step: str = Query("60s"),
    disable_tenant_filter: bool = False,
    user: AuthenticatedUser = Depends(require_scope("read:observability")),
) -> ResponseEnvelope[dict[str, Any]]:
    if disable_tenant_filter and not user.has_scope(SCOPE_ADMIN_CLUSTER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "error_description": (
                    "disable_tenant_filter requires admin:cluster"
                ),
            },
        )
    tenant_id = user.org_id or ""
    if not tenant_id and not disable_tenant_filter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "missing_tenant_claim",
                "error_description": (
                    "the JWT must carry an https://aqp.internal/org_id "
                    "claim for identity-aware Prometheus access"
                ),
            },
        )
    client = _prometheus_client()
    try:
        result = await client.query_range(
            expression=expression,
            tenant_id=tenant_id,
            start=start,
            end=end,
            step=step,
            disable_tenant_filter=disable_tenant_filter,
        )
    except PromQLDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "metric_denied",
                "metrics": list(exc.metrics),
            },
        ) from exc
    return ResponseEnvelope(
        status="ok",
        data={
            "rewritten_query": result.rewritten_query,
            "metrics_seen": list(result.metrics_seen),
            "tenant_id": tenant_id,
            "disable_tenant_filter": disable_tenant_filter,
            "data": result.data,
        },
    )


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
