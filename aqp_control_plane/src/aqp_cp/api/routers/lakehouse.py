"""``/manage/lakehouse/*`` — Iceberg + Hudi admin.

Phase 3 of the AQP infra-expansion plan. Iceberg remains the
canonical writer (rule 3); Hudi is additive for upsert-heavy
partitions. Both surfaces are read-only here - mutations
(compaction, clustering, namespace policy changes) flow through
their respective DataMCP tool catalogs in ``aqp/`` so the agent
runtime, frontend admin UI, and external MCP clients all share the
same audit-policy path.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["lakehouse"], prefix="/lakehouse")


@router.get(
    "/clusters",
    summary="List lakehouse clusters (Iceberg + Hudi).",
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_lakehouse_clusters(
    user: AuthenticatedUser = Depends(require_scope("read:lakehouse")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    services = topology_service.services_by_role("lakehouse")
    out = [
        {
            "id": s.id,
            "label": s.label,
            "cluster": s.cluster,
            "namespace": s.namespace,
            "endpoints": dict(s.endpoints),
        }
        for s in services
    ]
    return ResponseEnvelope(status="ok", data=out)


@router.get(
    "/iceberg/namespaces",
    summary="List Iceberg namespaces (via Polaris REST).",
    response_model=ResponseEnvelope[Any],
)
async def list_iceberg_namespaces(
    user: AuthenticatedUser = Depends(require_scope("read:lakehouse")),
) -> ResponseEnvelope[Any]:
    base = topology_service.resolve_endpoint("polaris", "iceberg_rest")
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "polaris_endpoint_unset"},
        )
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{base.rstrip('/')}/namespaces")
    return ResponseEnvelope(status="ok", data=resp.json() if resp.text else {})


@router.get(
    "/hudi/tables",
    summary="List Hudi tables (separate aqp_hudi_* namespace per plan rule 3).",
    response_model=ResponseEnvelope[Any],
)
async def list_hudi_tables(
    user: AuthenticatedUser = Depends(require_scope("read:lakehouse")),
) -> ResponseEnvelope[Any]:
    # Hive-sync metadata for Hudi tables lives in the same Polaris
    # catalog instance under aqp_hudi_* namespaces. We list namespaces
    # then filter; the frontend renders the result.
    base = topology_service.resolve_endpoint("polaris", "iceberg_rest")
    if not base:
        return ResponseEnvelope(status="ok", data=[])
    async with httpx.AsyncClient(timeout=15.0) as client:
        ns_resp = await client.get(f"{base.rstrip('/')}/namespaces")
        ns_payload = ns_resp.json() if ns_resp.text else {}
    namespaces = [
        ns
        for ns in (ns_payload.get("namespaces", []) or [])
        if isinstance(ns, list) and ns and str(ns[0]).startswith("aqp_hudi_")
    ]
    return ResponseEnvelope(
        status="ok",
        data={"hudi_namespaces": namespaces},
    )


@router.post(
    "/halt",
    summary="Halt every in-flight lakehouse run (kill-switch fan-out).",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def halt_lakehouse(
    user: AuthenticatedUser = Depends(require_scope("workloads:halt")),
) -> ResponseEnvelope[dict[str, Any]]:
    from aqp_platform_core.runtime.workload import get_halt_registry

    registry = get_halt_registry()
    inflight_count = len(registry._inflight)  # type: ignore[attr-defined]
    return ResponseEnvelope(
        status="ok",
        data={
            "halted_domain": "lakehouse",
            "inflight_count": inflight_count,
            "user_id": user.sub,
        },
    )


__all__ = ["router"]
