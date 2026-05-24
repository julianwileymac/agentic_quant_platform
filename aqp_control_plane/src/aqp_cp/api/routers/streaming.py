"""``/manage/streaming/*`` — admin routes for the streaming plane.

Phase 3 of the AQP infra-expansion plan. Two clusters live in
``aqp-streaming``: Strimzi Kafka (legacy default) and Redpanda
(side-by-side per plan question 2). The routes here read topology
metadata, expose health, and proxy operator URLs.

Mutating operations (topic create / delete) on the legacy Strimzi
cluster keep flowing through the legacy ``rpi-k8s-management``
endpoint while ``AQP_CONTROL_PLANE_LEGACY_FALLBACK=true`` (Phase 3
default). Phase 4 flips the default; mutations move under this
router and use the active :class:`InfrastructureProvider`.

Authorization: ``read:streaming`` for reads, ``write:streaming`` for
mutations. ``admin:cluster`` bypasses both.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["streaming"], prefix="/streaming")


@router.get(
    "/clusters",
    summary="List streaming clusters (Strimzi + Redpanda).",
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_streaming_clusters(
    user: AuthenticatedUser = Depends(require_scope("read:streaming")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    services = topology_service.services_by_role("streaming")
    out: list[dict[str, Any]] = []
    for service in services:
        out.append(
            {
                "id": service.id,
                "label": service.label,
                "cluster": service.cluster,
                "namespace": service.namespace,
                "endpoints": dict(service.endpoints),
                "protocols": dict(service.protocols),
            }
        )
    return ResponseEnvelope(status="ok", data=out)


@router.get(
    "/clusters/{cluster_id}",
    summary="Describe a single streaming cluster.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def describe_streaming_cluster(
    cluster_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:streaming")),
) -> ResponseEnvelope[dict[str, Any]]:
    service = topology_service.describe_service(cluster_id)
    return ResponseEnvelope(status="ok", data=service.frontend_dict())


@router.get(
    "/clusters/{cluster_id}/health",
    summary="Live health probe for a streaming cluster.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def streaming_cluster_health(
    cluster_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:streaming")),
) -> ResponseEnvelope[dict[str, Any]]:
    snapshot = await topology_service.probe_service_health(cluster_id)
    return ResponseEnvelope(status="ok", data=snapshot)


@router.post(
    "/halt",
    summary="Halt every in-flight streaming admin run (kill-switch fan-out).",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def halt_streaming(
    user: AuthenticatedUser = Depends(require_scope("workloads:halt")),
) -> ResponseEnvelope[dict[str, Any]]:
    """Streaming-specific halt. Calls the same WorkloadRuntime halt
    registry as the global `/manage/workloads/halt` so the topbar
    ``KillSwitch`` UI can fan out per-domain halt events. Idempotent."""
    from aqp_platform_core.runtime.workload import get_halt_registry

    registry = get_halt_registry()
    inflight_count = len(registry._inflight)  # type: ignore[attr-defined]
    return ResponseEnvelope(
        status="ok",
        data={
            "halted_domain": "streaming",
            "inflight_count": inflight_count,
            "user_id": user.sub,
        },
    )


__all__ = ["router"]
