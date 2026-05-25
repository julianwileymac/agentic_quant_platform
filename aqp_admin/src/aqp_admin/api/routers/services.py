# ruff: noqa: B008, ARG001
"""``/admin/services/*`` — managed-service catalog brokered to the CP."""
from __future__ import annotations

import logging
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin
from aqp_admin.integrations import AdminBrokerError, get_brokers
from aqp_admin.services.managed import ManagedServiceCatalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/services", tags=["services"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class ServiceNamespaceBody(BaseModel):
    namespace: str | None = None


class ServiceScaleBody(BaseModel):
    replicas: int = Field(..., ge=0, le=1000)
    namespace: str | None = None


@router.get(
    "",
    summary="List managed services across all tenant namespaces.",
)
async def list_services(
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin),
) -> dict[str, list[dict[str, object]]]:
    catalog = ManagedServiceCatalog()
    services = await catalog.list(namespace=namespace)
    return {
        "services": [
            {
                "id": s.id,
                "kind": s.kind,
                "org_id": s.org_id,
                "namespace": s.namespace,
                "state": s.state,
                "phase": s.phase,
                "image": s.image,
                "replicas_desired": s.replicas_desired,
                "replicas_ready": s.replicas_ready,
            }
            for s in services
        ],
    }


@router.get(
    "/{service_id}",
    summary="Read one managed service deployment status.",
)
async def get_service(
    service_id: str,
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin),
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


@router.post(
    "/{service_id}/restart",
    summary="Restart a managed service.",
)
async def restart_service(
    service_id: str,
    body: ServiceNamespaceBody | None = None,
    user: AdminUser = Depends(require_admin),
    audit: AuditContext = Depends(audit_context_dep("admin.services.restart")),
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


@router.patch(
    "/{service_id}/scale",
    summary="Scale a managed service.",
)
async def scale_service(
    service_id: str,
    body: ServiceScaleBody,
    user: AdminUser = Depends(require_admin),
    audit: AuditContext = Depends(audit_context_dep("admin.services.scale")),
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


@router.post(
    "/{service_id}/stop",
    summary="Stop a managed service.",
)
async def stop_service(
    service_id: str,
    body: ServiceNamespaceBody | None = None,
    user: AdminUser = Depends(require_admin),
    audit: AuditContext = Depends(audit_context_dep("admin.services.stop")),
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


@router.get(
    "/{service_id}/logs",
    summary="Read a bounded managed-service log snapshot.",
)
async def service_logs(
    service_id: str,
    namespace: str | None = None,
    container: str | None = None,
    tail: int = 200,
    user: AdminUser = Depends(require_admin),
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


__all__ = ["router"]
