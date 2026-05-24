"""``/manage/topology`` — service-topology snapshot + lookup routes.

Phase 0 of the AQP infra-expansion plan. The single source of truth
for "what services exist, where do they live, what URLs do they
expose" is ``configs/deployment/topology.yaml``. This router exposes
that map over HTTP so:

- AQP-side processes can fall back to topology values for URL fields
  via :mod:`aqp.config.topology_fallback`.
- The frontend admin pages can render topology dashboards.
- Agent ``data.topology.*`` MCP tools can read service metadata
  through one canonical endpoint.

Authorization: ``read:topology`` for the snapshot/list/get routes;
``admin:cluster`` for the reload route. ``admin:cluster`` bypasses
the scope check (existing platform behavior).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["topology"], prefix="/topology")


@router.get(
    "",
    summary="Full topology snapshot.",
    description=(
        "Returns the entire ``configs/deployment/topology.yaml`` content "
        "validated through the shared ``DeploymentTopology`` Pydantic model. "
        "AQP-side processes hit this endpoint to back-fill URL settings "
        "without an active env override. Required scope: "
        "``read:topology`` (admin:cluster bypass)."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def topology_snapshot(
    include_targets: bool = True,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    return ResponseEnvelope(status="ok", data=topology_service.snapshot(include_targets))


@router.get(
    "/services",
    summary="List every service descriptor.",
    description=(
        "Returns every ``ServiceDefinition`` declared in the topology. "
        "Optionally filterable by ``role`` (e.g., ``streaming``, "
        "``observability``, ``lakehouse``) or ``cluster`` (e.g., "
        "``streaming.strimzi``, ``streaming.redpanda``)."
    ),
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def list_services(
    role: str | None = None,
    cluster: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    if role and cluster:
        services = [
            s for s in topology_service.services_by_role(role)
            if s.cluster == cluster
        ]
    elif role:
        services = topology_service.services_by_role(role)
    elif cluster:
        services = topology_service.services_by_cluster(cluster)
    else:
        services = topology_service.get_topology().services
    return ResponseEnvelope(
        status="ok",
        data=[service.model_dump() for service in services],
    )


@router.get(
    "/services/{service_id}",
    summary="Single service descriptor.",
    description=(
        "Returns the ``ServiceDefinition`` for ``service_id`` (matched "
        "either by ``id`` or by ``aliases``). 404 if unknown."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def get_service(
    service_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    service = topology_service.describe_service(service_id)
    return ResponseEnvelope(status="ok", data=service.frontend_dict())


@router.get(
    "/services/{service_id}/endpoint",
    summary="Resolve a service endpoint URL.",
    description=(
        "Returns the URL for the named endpoint (e.g., ``bootstrap``, "
        "``ui``, ``otlp``, ``ilp``). When ``name`` is omitted, returns "
        "the service's primary URL (resolution order: ``bootstrap`` -> "
        "``ui`` -> ``http`` -> ``api`` -> ``admin`` -> first declared)."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def resolve_endpoint(
    service_id: str,
    name: str = "",
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    url = topology_service.resolve_endpoint(service_id, name)
    return ResponseEnvelope(
        status="ok",
        data={
            "service_id": service_id,
            "endpoint": name or "primary",
            "url": url,
        },
    )


@router.get(
    "/services/{service_id}/health",
    summary="Live health probe for a service.",
    description=(
        "Calls into the active ``InfrastructureProvider.list_deployments`` "
        "for the service's namespace and returns its phase + replica counts. "
        "Best-effort; returns ``status='unknown'`` with the provider error "
        "code when the call fails."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def service_health(
    service_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    return ResponseEnvelope(
        status="ok",
        data=await topology_service.probe_service_health(service_id),
    )


@router.get(
    "/targets",
    summary="List every deployment target.",
    description=(
        "Returns the ``targets`` map (local / rpi / future cloud overlays)."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def list_targets(
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    topology = topology_service.get_topology()
    return ResponseEnvelope(
        status="ok",
        data={
            "active": topology_service._active_target_id(),  # noqa: SLF001
            "targets": {
                target_id: target.summary_dict()
                for target_id, target in topology.targets.items()
            },
        },
    )


@router.get(
    "/targets/{target_id}",
    summary="Single deployment target descriptor.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def get_target(
    target_id: str,
    user: AuthenticatedUser = Depends(require_scope("read:topology")),
) -> ResponseEnvelope[dict[str, Any]]:
    topology = topology_service.get_topology()
    try:
        target = topology.target(target_id)
    except KeyError as exc:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "target_unknown",
                "error_description": str(exc),
                "available": sorted(topology.targets.keys()),
            },
        ) from exc
    return ResponseEnvelope(status="ok", data=target.model_dump())


@router.post(
    "/reload",
    summary="Drop the topology cache and reload from disk.",
    description=(
        "Reloads ``configs/deployment/topology.yaml`` from disk. Useful "
        "after editing the file in-place during development. Production "
        "deployments should restart the control-plane pod instead. "
        "Required scope: ``admin:cluster``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def reload_topology(
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[dict[str, Any]]:
    topology = topology_service.reload()
    return ResponseEnvelope(
        status="ok",
        data={
            "version": topology.version,
            "service_count": len(topology.services),
            "target_count": len(topology.targets),
        },
    )


__all__ = ["router"]
