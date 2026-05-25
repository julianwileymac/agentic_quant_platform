# ruff: noqa: B008, ARG001
"""``/admin/deployments`` — audit-first workload administration.

The admin BFF never talks to Kubernetes, Docker, or cloud SDKs directly.
Every workload action is brokered to ``aqp_control_plane`` where the
active ``InfrastructureProvider`` and ``WorkloadRuntime`` own execution.
"""
from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/deployments", tags=["deployments"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class DeploymentStartBody(BaseModel):
    spec: dict[str, Any]


class DeploymentScaleBody(BaseModel):
    replicas: int = Field(..., ge=0, le=1000)
    namespace: str | None = None


class DeploymentNamespaceBody(BaseModel):
    namespace: str | None = None


class DeploymentExecBody(BaseModel):
    command: list[str] = Field(..., min_length=1)
    container: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    stdin_b64: str | None = None
    namespace: str | None = None


@router.get("", summary="List deployments visible through the control plane.")
async def list_deployments(
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.list_deployments(namespace=namespace)
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/halt/status", summary="Inspect WorkloadRuntime halt status.")
async def workloads_halt_status(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.workloads_halt_status(
            bearer_passthrough=_bearer_from_header(authorization)
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/{service_id}", summary="Read one deployment status.")
async def get_deployment(
    service_id: str,
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.get_deployment(
            service_id,
            namespace=namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post("/{service_id}/start", summary="Start or update a deployment.")
async def start_deployment(
    service_id: str,
    body: DeploymentStartBody,
    user: AdminUser = Depends(require_admin_scope("manage:agents")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.start")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = service_id
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().control_plane.start_deployment(
            service_id,
            body.spec,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"service_id": service_id})
    return {"result": result, "audit_run_id": audit.run_id}


@router.post("/{service_id}/stop", summary="Stop a deployment by scaling to zero.")
async def stop_deployment(
    service_id: str,
    body: DeploymentNamespaceBody | None = None,
    user: AdminUser = Depends(require_admin_scope("manage:agents")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.stop")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    namespace = body.namespace if body else None
    audit.target = service_id
    audit.start(payload={"namespace": namespace})
    try:
        result = await get_brokers().control_plane.stop_deployment(
            service_id,
            namespace=namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"service_id": service_id, "namespace": namespace})
    return {"result": result, "audit_run_id": audit.run_id}


@router.patch("/{service_id}/scale", summary="Scale a deployment.")
async def scale_deployment(
    service_id: str,
    body: DeploymentScaleBody,
    user: AdminUser = Depends(require_admin_scope("manage:agents")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.scale")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = service_id
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().control_plane.scale_deployment(
            service_id,
            replicas=body.replicas,
            namespace=body.namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed(
        {"service_id": service_id, "namespace": body.namespace, "replicas": body.replicas}
    )
    return {"result": result, "audit_run_id": audit.run_id}


@router.post("/{service_id}/restart", summary="Restart a deployment.")
async def restart_deployment(
    service_id: str,
    body: DeploymentNamespaceBody | None = None,
    user: AdminUser = Depends(require_admin_scope("manage:agents")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.restart")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    namespace = body.namespace if body else None
    audit.target = service_id
    audit.start(payload={"namespace": namespace})
    try:
        result = await get_brokers().control_plane.restart_deployment(
            service_id,
            namespace=namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"service_id": service_id, "namespace": namespace})
    return {"result": result, "audit_run_id": audit.run_id}


@router.post("/{service_id}/exec", summary="Execute a command in a deployment container.")
async def exec_deployment(
    service_id: str,
    body: DeploymentExecBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.exec")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = service_id
    audit_payload = body.model_dump()
    if audit_payload.get("stdin_b64"):
        audit_payload["stdin_b64"] = "<redacted>"
    audit.start(payload=audit_payload)
    try:
        result = await get_brokers().control_plane.exec_deployment(
            service_id,
            body.model_dump(),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"service_id": service_id, "namespace": body.namespace})
    return {"result": result, "audit_run_id": audit.run_id}


@router.get("/{service_id}/logs", summary="Read a bounded deployment log snapshot.")
async def deployment_logs(
    service_id: str,
    namespace: str | None = None,
    container: str | None = None,
    tail: int = 200,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.deployment_logs(
            service_id,
            namespace=namespace,
            container=container,
            tail=tail,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.delete("/{service_id}", summary="Tear down a deployment by scale-to-zero.")
async def delete_deployment(
    service_id: str,
    body: DeploymentNamespaceBody | None = None,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.deployments.delete")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    namespace = body.namespace if body else None
    audit.target = service_id
    audit.start(payload={"namespace": namespace})
    try:
        result = await get_brokers().control_plane.delete_deployment(
            service_id,
            namespace=namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"service_id": service_id, "namespace": namespace})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
