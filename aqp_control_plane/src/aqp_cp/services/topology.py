"""Topology service — single source of truth for service URLs.

Phase 0 of the AQP infra-expansion plan. The topology YAML at
``aqp_platform/configs/deployment/topology.yaml`` is the canonical map of service
metadata (workload kind, ports, namespaces, endpoints) for every
target environment. AQP-side ``aqp.config.settings`` falls back to
this map when a URL field has not been overridden by an
``AQP_*`` env var.

The service exposes:

- :func:`get_topology` — cached loader using
  :func:`aqp_platform_core.topology.load_topology`.
- :func:`snapshot` — return the full topology with health probes
  attached when ``include_health=True``.
- :func:`describe_service` — single service descriptor (404 if
  unknown).
- :func:`resolve_endpoint` — convenience for pulling a named endpoint
  URL out of a service descriptor.
- :func:`services_by_role` / :func:`services_by_cluster` — filtered
  views used by the UI dropdowns.

The service deliberately does not call :class:`InfrastructureProvider`
methods unless ``include_health=True``. This keeps the snapshot path
cheap (it is on every settings-fallback hit and every frontend page
load) and reserves provider calls for explicit health endpoints.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from aqp_platform_core.providers import InfrastructureProviderError
from aqp_platform_core.topology import (
    DeploymentTarget,
    DeploymentTopology,
    ServiceDefinition,
    TopologyLoadError,
    load_topology,
    reload_topology,
)

from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)


def get_topology() -> DeploymentTopology:
    """Return the cached topology or raise an HTTP 503 with the path."""
    try:
        return load_topology()
    except TopologyLoadError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "topology_unavailable",
                "error_description": str(exc),
                "path": exc.path,
            },
        ) from exc


def reload() -> DeploymentTopology:
    """Drop the cache and reload from disk. Used by ``POST /topology/reload``."""
    try:
        return reload_topology()
    except TopologyLoadError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "topology_unavailable",
                "error_description": str(exc),
                "path": exc.path,
            },
        ) from exc


def _active_target_id() -> str:
    """Resolve the active deployment target from control-plane settings."""
    settings = get_settings()
    if settings.topology_target_id:
        return settings.topology_target_id

    # Provider alias fallback:
    # - docker_compose => local
    # - kubernetes/cloud providers => first non-local kubernetes-like target
    if settings.provider == "docker_compose":
        return "local"

    topology = get_topology()
    for target_id in sorted(topology.targets.keys()):
        target = topology.targets[target_id]
        if target.kind in {"kubernetes", "rpi_cluster"} and target_id != "local":
            return target_id
    if "rpi" in topology.targets:
        return "rpi"
    return sorted(topology.targets.keys())[0]


def active_target() -> DeploymentTarget:
    topology = get_topology()
    target_id = _active_target_id()
    try:
        return topology.target(target_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "target_unknown",
                "error_description": str(exc),
                "available": sorted(topology.targets.keys()),
            },
        ) from exc


def describe_service(service_id: str) -> ServiceDefinition:
    """Return one :class:`ServiceDefinition` or HTTP 404."""
    topology = get_topology()
    service = topology.service_map.get(service_id)
    if service is not None:
        return service
    # Try alias resolution.
    for candidate in topology.services:
        if service_id in candidate.aliases:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "service_unknown",
            "error_description": f"unknown service id {service_id!r}",
            "available": sorted(topology.service_map.keys()),
        },
    )


def services_by_role(role: str) -> list[ServiceDefinition]:
    topology = get_topology()
    return [s for s in topology.services if s.role == role]


def services_by_cluster(cluster: str) -> list[ServiceDefinition]:
    topology = get_topology()
    return [s for s in topology.services if s.cluster == cluster]


def resolve_endpoint(service_id: str, endpoint_name: str = "") -> str | None:
    """Return a named endpoint URL or the service's primary URL."""
    service = describe_service(service_id)
    if endpoint_name:
        return service.endpoint(endpoint_name)
    return service.primary_url()


async def probe_service_health(service_id: str) -> dict[str, Any]:
    """Best-effort liveness probe via the active provider."""
    from aqp_cp.services.lifecycle import get_active_provider

    service = describe_service(service_id)
    provider = get_active_provider()
    target = active_target()
    namespace = service.namespace or target.namespace
    try:
        deployments = await provider.list_deployments(namespace=namespace)
    except InfrastructureProviderError as exc:
        return {
            "service_id": service.id,
            "namespace": namespace,
            "status": "unknown",
            "error": exc.code,
            "detail": str(exc),
        }
    matching = [
        d for d in deployments
        if (
            getattr(d, "name", None) == service.app_label
            or getattr(d, "id", None) == service.app_label
        )
    ]
    if not matching:
        return {
            "service_id": service.id,
            "namespace": namespace,
            "status": "absent",
        }
    deployment = matching[0]
    return {
        "service_id": service.id,
        "namespace": namespace,
        "status": getattr(deployment, "phase", "unknown"),
        "replicas": {
            "desired": getattr(deployment, "replicas_desired", None),
            "ready": getattr(deployment, "replicas_ready", None),
        },
    }


def snapshot(include_targets: bool = True) -> dict[str, Any]:
    """Return a JSON-friendly view of the entire topology.

    Used by the new ``GET /manage/topology`` route and by
    :mod:`aqp.config.topology_fallback` to back-fill URL settings on
    AQP-side processes.
    """
    topology = get_topology()
    payload: dict[str, Any] = {
        "version": topology.version,
        "defaults": topology.defaults.model_dump(),
        "services": [service.model_dump() for service in topology.services],
    }
    if include_targets:
        payload["targets"] = {
            target_id: target.model_dump()
            for target_id, target in topology.targets.items()
        }
    payload["active_target_id"] = _active_target_id()
    return payload


__all__ = [
    "active_target",
    "describe_service",
    "get_topology",
    "probe_service_health",
    "reload",
    "resolve_endpoint",
    "services_by_cluster",
    "services_by_role",
    "snapshot",
]
