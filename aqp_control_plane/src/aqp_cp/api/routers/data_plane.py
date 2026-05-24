"""``/manage/data-plane/*`` — single admin surface for the data plane.

Phase 3 of the AQP infra-expansion plan. Re-homes the legacy
``rpi-k8s-management`` ``/api/{kafka,flink,redis,minio,mlflow}``
endpoints under a consolidated ``/manage/data-plane/*`` router.
Read-only here; mutating operations land in the corresponding
``InfrastructureProvider`` subclass (Phase 3 follow-up + Phase 4
flip).

The router enumerates one read endpoint per data-plane service:

- ``/manage/data-plane/services`` — full topology listing.
- ``/manage/data-plane/{service_id}`` — single-service descriptor.
- ``/manage/data-plane/{service_id}/health`` — provider-driven probe.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["data-plane"], prefix="/data-plane")


_DATA_PLANE_ROLES = (
    "database",
    "cache",
    "storage",
    "metadata",
    "vector-store",
    "elt",
    "mlops",
    "orchestration",
    "lakehouse",
    "timeseries",
)


@router.get(
    "/services",
    summary="List every data-plane service known to the topology.",
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_data_plane_services(
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    topology = topology_service.get_topology()
    out = [
        {
            "id": s.id,
            "label": s.label,
            "role": s.role,
            "namespace": s.namespace,
            "endpoints": dict(s.endpoints),
        }
        for s in topology.services
        if s.role in _DATA_PLANE_ROLES
    ]
    return ResponseEnvelope(status="ok", data=out)


@router.get(
    "/services/{service_id}",
    summary="Single data-plane service descriptor.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def describe_data_plane_service(
    service_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    service = topology_service.describe_service(service_id)
    return ResponseEnvelope(status="ok", data=service.frontend_dict())


@router.get(
    "/services/{service_id}/health",
    summary="Live health probe for a data-plane service.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def data_plane_service_health(
    service_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    snapshot = await topology_service.probe_service_health(service_id)
    return ResponseEnvelope(status="ok", data=snapshot)


__all__ = ["router"]
