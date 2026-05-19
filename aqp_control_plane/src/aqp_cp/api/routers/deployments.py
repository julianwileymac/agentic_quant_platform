"""``/manage/deployments`` — list / start / stop / scale / status / delete."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from aqp_cp.auth.deps import (
    AuthenticatedUser,
    filter_resources_for_user,
    require_auth,
    require_scope,
)
from aqp_cp.models import (
    DeploymentSpec,
    DeploymentStatus,
    ResponseEnvelope,
    WorkloadAction,
)
from aqp_cp.services.lifecycle import execute_with_audit, get_active_provider

router = APIRouter(tags=["deployments"])


@router.get(
    "/deployments",
    summary="List deployments visible to the authenticated user.",
    description=(
        "Returns the deployments the active provider knows about, filtered "
        "through ``filter_resources(items, payload)`` so users only see "
        "resources whose id is in their ``https://aqp.internal/resources`` "
        "claim. Operators with ``admin:cluster`` bypass the filter."
    ),
    response_model=ResponseEnvelope[list[DeploymentStatus]],
)
async def list_deployments(
    request: Request,
    namespace: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[list[DeploymentStatus]]:
    provider = get_active_provider()
    items = await provider.list_deployments(namespace=namespace)
    filtered = filter_resources_for_user(
        items, user, id_getter=lambda d: d.service_id
    )
    return ResponseEnvelope(status="ok", data=filtered)


@router.get(
    "/deployments/{service_id}",
    summary="Read the status of one deployment.",
    response_model=ResponseEnvelope[DeploymentStatus],
)
async def get_deployment(
    service_id: str,
    request: Request,
    namespace: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[DeploymentStatus]:
    provider = get_active_provider()
    status_obj = await provider.status(service_id, namespace=namespace)
    return ResponseEnvelope(status="ok", data=status_obj)


@router.post(
    "/deployments/{service_id}/start",
    summary="Start (or update) a deployment.",
    response_model=ResponseEnvelope[DeploymentStatus],
)
async def start_deployment(
    service_id: str,
    spec: DeploymentSpec,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:agents")),
) -> ResponseEnvelope[DeploymentStatus]:
    if spec.service_id != service_id:
        spec = spec.model_copy(update={"service_id": service_id})
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.START,
        target=service_id,
        user=user,
        payload=spec.model_dump(mode="json"),
        fn=lambda: provider.start(spec),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/deployments/{service_id}/stop",
    summary="Stop a deployment (scale to zero).",
    response_model=ResponseEnvelope[DeploymentStatus],
)
async def stop_deployment(
    service_id: str,
    request: Request,
    namespace: str | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:agents")),
) -> ResponseEnvelope[DeploymentStatus]:
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.STOP,
        target=service_id,
        user=user,
        payload={"namespace": namespace},
        fn=lambda: provider.stop(service_id, namespace=namespace),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.patch(
    "/deployments/{service_id}/scale",
    summary="Scale a deployment to the requested replica count.",
    response_model=ResponseEnvelope[DeploymentStatus],
)
async def scale_deployment(
    service_id: str,
    replicas: int,
    request: Request,
    namespace: str | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:agents")),
) -> ResponseEnvelope[DeploymentStatus]:
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.SCALE,
        target=service_id,
        user=user,
        payload={"replicas": replicas, "namespace": namespace},
        fn=lambda: provider.scale(service_id, replicas, namespace=namespace),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.delete(
    "/deployments/{service_id}",
    summary="Tear down a deployment (admin:cluster only).",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def delete_deployment(
    service_id: str,
    request: Request,
    namespace: str | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[dict[str, Any]]:
    # The current ABC doesn't define a delete primitive — stop+scale-to-0
    # is the safest cross-cloud teardown. Real deletion (resource group /
    # namespace teardown) is a follow-up.
    provider = get_active_provider()
    _run, _result = await execute_with_audit(
        action=WorkloadAction.DELETE,
        target=service_id,
        user=user,
        payload={"namespace": namespace},
        fn=lambda: provider.stop(service_id, namespace=namespace),
        request_id=x_request_id,
    )
    return ResponseEnvelope(
        status="ok",
        data={
            "service_id": service_id,
            "namespace": namespace,
            "note": "Stopped via scale-to-zero. Hard delete is a follow-up PR.",
        },
    )


__all__ = ["router"]
