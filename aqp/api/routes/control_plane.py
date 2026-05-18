"""Authenticated AQP control-plane routes.

This router exposes high-level deployment and cluster-status operations
for the Vite Control Plane UI. Mutating deployment actions dispatch to
TerraformRuntime via Celery tasks; live cluster reads go through the
active KubernetesAdapter (rpi_cluster for the Raspberry Pi cluster).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from aqp.api.schemas import TaskAccepted
from aqp.api.security import require_authenticated, secure_router
from aqp.auth import CurrentUser
from aqp.config import settings
from aqp.deployment.topology import (
    DeploymentTarget,
    ServiceDefinition,
    get_deployment_topology,
)
from aqp.deployment.topology import (
    list_targets as list_topology_targets,
)

logger = logging.getLogger(__name__)

router = secure_router(prefix="/control-plane", tags=["control-plane"])


class TargetSummary(BaseModel):
    id: str
    label: str
    kind: str
    namespace: str


class TargetStatus(BaseModel):
    target: str
    available: bool
    adapter: dict[str, Any]
    pods: list[dict[str, Any]]
    namespace: str
    services: list[dict[str, Any]]


class IdentityStatus(BaseModel):
    provider: str
    required: bool
    oidc_issuer: str
    oidc_audience: str
    oidc_client_id_configured: bool
    scim_enabled: bool
    scim_endpoint: str = "/scim/v2"
    scim_patch_supported: bool = True


@router.get("/topology")
def deployment_topology(
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Return frontend-safe deployment topology metadata."""
    return get_deployment_topology().frontend_dict()


@router.get("/identity", response_model=IdentityStatus)
def identity_status(
    user: CurrentUser = Depends(require_authenticated),
) -> IdentityStatus:
    """Return operator-safe identity status without requiring SCIM bearer auth."""
    return IdentityStatus(
        provider=settings.auth_provider,
        required=bool(settings.auth_required),
        oidc_issuer=settings.auth_oidc_issuer,
        oidc_audience=settings.auth_oidc_audience,
        oidc_client_id_configured=bool(settings.auth_oidc_client_id),
        scim_enabled=bool(settings.auth_scim_enabled),
    )


@router.get("/kubernetes/targets", response_model=list[TargetSummary])
def list_targets(user: CurrentUser = Depends(require_authenticated)) -> list[TargetSummary]:
    return [
        TargetSummary(**target.summary_dict())
        for target in list_topology_targets()
    ]


@router.get("/kubernetes/targets/{target}/status", response_model=TargetStatus)
def target_status(
    target: str,
    user: CurrentUser = Depends(require_authenticated),
) -> TargetStatus:
    target_def = _target_definition(target)
    adapter = _adapter_for_target(target)
    namespace = target_def.namespace
    pods: list[dict[str, Any]] = []
    try:
        pods = [_pod_info_dict(p) for p in adapter.list_pods(namespace=namespace)]
    except Exception as exc:  # noqa: BLE001
        logger.debug("target_status pod list failed: %s", exc, exc_info=True)
    return TargetStatus(
        target=target,
        available=bool(adapter.is_available()),
        adapter=adapter.describe(),
        pods=pods,
        namespace=namespace,
        services=[
            service.frontend_dict()
            for service in get_deployment_topology().services_for_target(target)
        ],
    )


@router.post("/kubernetes/targets/{target}/deploy", response_model=TaskAccepted)
def deploy_target(
    target: str,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    return _enqueue_target(target=target, action="up")


@router.post("/kubernetes/targets/{target}/destroy", response_model=TaskAccepted)
def destroy_target(
    target: str,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    return _enqueue_target(target=target, action="down")


@router.post("/kubernetes/targets/{target}/restart")
def restart_target(
    target: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    target_def = _target_definition(target)
    adapter = _adapter_for_target(target)
    namespace = target_def.namespace
    service = _default_restart_service(target_def)
    # Restart the API deployment first; workers can be restarted via
    # the same route once frontend exposes per-service controls.
    scaled = adapter.scale_deployment(namespace=namespace, name=service.id, replicas=0)
    restored = adapter.scale_deployment(namespace=namespace, name=service.id, replicas=1)
    return {"ok": True, "service": service.id, "scaled": scaled, "restored": restored}


@router.get("/kubernetes/targets/{target}/logs")
def target_logs(
    target: str,
    service: str = "aqp-api",
    tail_lines: int = 200,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    target_def = _target_definition(target)
    service_def = _service_definition(target=target, service=service)
    adapter = _adapter_for_target(target)
    namespace = target_def.namespace
    pod_name = _resolve_pod_name_for_logs(
        adapter=adapter,
        namespace=namespace,
        service=service_def.id,
        app_label=service_def.app_label,
    )
    return {
        "target": target,
        "service": service,
        "pod_name": pod_name,
        "logs": adapter.pod_logs(
            namespace=namespace, name=pod_name, tail_lines=tail_lines
        ),
    }


def _target_definition(target: str) -> DeploymentTarget:
    try:
        return get_deployment_topology().target(target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown target {target!r}") from exc


def _pod_info_dict(pod: Any) -> dict[str, Any]:
    if is_dataclass(pod):
        return asdict(pod)
    if isinstance(pod, dict):
        return dict(pod)
    return {
        key: getattr(pod, key)
        for key in (
            "namespace",
            "name",
            "phase",
            "node",
            "pod_ip",
            "started_at",
            "containers",
            "labels",
        )
        if hasattr(pod, key)
    }


def _adapter_for_target(target: str):
    target_def = _target_definition(target)
    if target_def.kind == "local":
        from aqp.kubernetes.adapters.in_cluster import InClusterAdapter
        from aqp.kubernetes.adapters.local_compose import LocalComposeAdapter

        # The local control-plane target is Terraform+k3d based. Prefer
        # the Kubernetes SDK adapter (kubeconfig/in-cluster) and fall
        # back to the compose adapter only when Kubernetes isn't
        # reachable on this host.
        in_cluster = InClusterAdapter()
        if in_cluster.is_available():
            return in_cluster
        return LocalComposeAdapter()
    from aqp.kubernetes import get_kubernetes_adapter

    return get_kubernetes_adapter()


def _enqueue_target(*, target: str, action: str) -> TaskAccepted:
    target_def = _target_definition(target)
    try:
        if target_def.kind == "rpi_cluster":
            from aqp.tasks.terraform_tasks import run_rpi_stack

            async_result = run_rpi_stack.apply_async(
                kwargs={"action": action, "spec_name": target_def.terraform.stack_slug}
            )
        elif target_def.kind == "local":
            from aqp.tasks.terraform_tasks import run_local_stack

            async_result = run_local_stack.apply_async(
                kwargs={"action": action, "spec_name": target_def.terraform.stack_slug}
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"target {target!r} has no deployment task mapping",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=(
                f"failed to enqueue terraform {action!r} for target {target!r}: {exc}. "
                "Check that the Celery broker and worker are reachable."
            ),
        ) from exc

    task_id = str(async_result.id)
    return TaskAccepted(
        task_id=task_id,
        status="accepted",
        stream_url=f"/ws/terraform/runs/{task_id}",
    )


def _service_definition(*, target: str, service: str) -> ServiceDefinition:
    topology = get_deployment_topology()
    services = {item.id: item for item in topology.services_for_target(target)}
    try:
        return services[service]
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"unknown service {service!r} for target {target!r}",
        ) from exc


def _default_restart_service(target: DeploymentTarget) -> ServiceDefinition:
    topology = get_deployment_topology()
    for service in topology.services_for_target(target.id):
        if service.role == "api" and service.restartable:
            return service
    raise HTTPException(
        status_code=409,
        detail=f"target {target.id!r} has no restartable API service",
    )


def _resolve_pod_name_for_logs(
    *,
    adapter: Any,
    namespace: str,
    service: str,
    app_label: str | None = None,
) -> str:
    """Best-effort service/deployment -> pod-name resolution for logs."""
    label = app_label or service
    try:
        candidates = adapter.list_pods(
            namespace=namespace, label_selector=f"app={label}"
        )
        if candidates:
            return candidates[0].name
    except Exception:  # noqa: BLE001
        logger.debug(
            "pod lookup by label failed for service=%s namespace=%s",
            service,
            namespace,
            exc_info=True,
        )
    try:
        candidates = adapter.list_pods(namespace=namespace)
        for pod in candidates:
            if pod.name == service or pod.name.startswith(f"{service}-"):
                return pod.name
    except Exception:  # noqa: BLE001
        logger.debug(
            "pod lookup by namespace failed for service=%s namespace=%s",
            service,
            namespace,
            exc_info=True,
        )
    return service


__all__ = ["router"]
