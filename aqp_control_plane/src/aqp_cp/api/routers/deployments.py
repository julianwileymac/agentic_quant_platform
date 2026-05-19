"""``/manage/deployments`` — list / start / stop / scale / status / delete."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

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
from aqp_platform_core.models.workloads import WorkloadExecResult, WorkloadLogEvent

router = APIRouter(tags=["deployments"])


class ExecRequest(BaseModel):
    """Request body for executing a command inside a deployment/container."""

    command: list[str] = Field(..., min_length=1)
    container: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    stdin_b64: str | None = None
    namespace: str | None = None


class LogsResponse(BaseModel):
    """Bounded log snapshot for one deployment."""

    service_id: str
    namespace: str | None = None
    events: list[WorkloadLogEvent] = Field(default_factory=list)


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


@router.post(
    "/deployments/{service_id}/restart",
    summary="Restart a deployment.",
    response_model=ResponseEnvelope[DeploymentStatus],
)
async def restart_deployment(
    service_id: str,
    request: Request,
    namespace: str | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:agents")),
) -> ResponseEnvelope[DeploymentStatus]:
    provider = get_active_provider()
    _run, result = await execute_with_audit(
        action=WorkloadAction.RESTART,
        target=service_id,
        user=user,
        payload={"namespace": namespace},
        fn=lambda: provider.restart(service_id, namespace=namespace),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/deployments/{service_id}/exec",
    summary="Execute a command inside a deployment/container.",
    response_model=ResponseEnvelope[WorkloadExecResult],
)
async def exec_deployment(
    service_id: str,
    body: ExecRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:infrastructure")),
) -> ResponseEnvelope[WorkloadExecResult]:
    provider = get_active_provider()
    stdin = None
    if body.stdin_b64:
        import base64

        stdin = base64.b64decode(body.stdin_b64)
    _run, result = await execute_with_audit(
        action=WorkloadAction.EXEC,
        target=service_id,
        user=user,
        payload=body.model_dump(mode="json"),
        fn=lambda: provider.exec(
            service_id,
            command=body.command,
            container=body.container,
            timeout_seconds=body.timeout_seconds,
            stdin=stdin,
            namespace=body.namespace,
        ),
        request_id=x_request_id,
    )
    return ResponseEnvelope(status="ok", data=result)


@router.get(
    "/deployments/{service_id}/logs",
    summary="Read a bounded log snapshot for a deployment.",
    response_model=ResponseEnvelope[LogsResponse],
)
async def deployment_logs(
    service_id: str,
    request: Request,
    namespace: str | None = None,
    container: str | None = None,
    tail: int = 200,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[LogsResponse]:
    provider = get_active_provider()
    payload = {
        "namespace": namespace,
        "container": container,
        "tail": tail,
        "follow": False,
    }

    async def _collect_logs() -> LogsResponse:
        events: list[WorkloadLogEvent] = []
        async for event in provider.tail_logs(
            service_id,
            container=container,
            tail=tail,
            follow=False,
            namespace=namespace,
        ):
            events.append(event)
            if len(events) >= tail:
                break
        return LogsResponse(service_id=service_id, namespace=namespace, events=events)

    _run, result = await execute_with_audit(
        action=WorkloadAction.LOGS,
        target=service_id,
        user=user,
        payload=payload,
        fn=_collect_logs,
        request_id=x_request_id,
    )
    return ResponseEnvelope(
        status="ok",
        data=result,
    )


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
