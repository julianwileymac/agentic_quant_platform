# ruff: noqa: B008, ARG001
"""``/admin/kubernetes`` — brokered cluster and pod diagnostics.

Deployment-level workload mutations belong to ``/admin/deployments`` and
the control plane. This router only exposes cluster status and pod-level
diagnostics that are currently available through the monolith's
``KubernetesAdapter`` route surface.
"""
from __future__ import annotations

import re
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/kubernetes", tags=["kubernetes"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class PodExecBody(BaseModel):
    command: list[str] = Field(..., min_length=1)
    container: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    stdin_b64: str | None = None


class PodArchivePutBody(BaseModel):
    path: str = Field(..., min_length=1)
    data_b64: str = Field(..., min_length=1)
    container: str | None = None


@router.get("/status", summary="Read active Kubernetes adapter status.")
async def cluster_status(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.cluster_status(
            bearer_passthrough=_bearer_from_header(authorization)
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/namespaces", summary="List namespaces inferred from managed deployments.")
async def namespaces(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    bearer = _bearer_from_header(authorization)
    try:
        payload = await get_brokers().control_plane.list_deployments()
    except AdminBrokerError as exc:
        _raise_broker_error(exc)
    rows = payload.get("data") if isinstance(payload, dict) else []
    namespaces_by_name: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        namespace = str(row.get("namespace") or "")
        if not namespace:
            continue
        entry = namespaces_by_name.setdefault(
            namespace,
            {"namespace": namespace, "deployment_count": 0, "ready": 0, "desired": 0},
        )
        entry["deployment_count"] += 1
        entry["ready"] += int(row.get("replicas_ready") or 0)
        entry["desired"] += int(row.get("replicas_desired") or 0)
    return {
        "namespaces": sorted(namespaces_by_name.values(), key=lambda item: item["namespace"]),
        "source": "control_plane.deployments",
        "bearer_passthrough": bool(bearer),
    }


@router.get("/pods/{namespace}", summary="List pods in a namespace.")
async def list_pods(
    namespace: str,
    label_selector: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        pods = await get_brokers().monolith.list_pods(
            namespace,
            label_selector=label_selector,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)
    return {"namespace": namespace, "pods": pods}


@router.get("/pods/{namespace}/{name}/logs/stream-url", summary="Return pod log stream URL.")
async def pod_log_stream_url(
    namespace: str,
    name: str,
    container: str | None = None,
    tail_lines: int | None = Query(default=200, ge=1, le=10000),
    follow: bool = True,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
) -> dict[str, Any]:
    params = [f"tail_lines={tail_lines}", f"follow={str(follow).lower()}"]
    if container:
        params.append(f"container={container}")
    query = "&".join(params)
    return {
        "namespace": namespace,
        "name": name,
        "stream_url": f"/cluster/pods/{namespace}/{name}/logs/stream?{query}",
        "auth_protocol": "first-frame-token",
    }


@router.post("/pods/{namespace}/{name}/exec", summary="Execute a pod command.")
async def exec_in_pod(
    namespace: str,
    name: str,
    body: PodExecBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.kubernetes.pod.exec")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = f"{namespace}/{name}"
    audit_payload = {"namespace": namespace, "name": name, **body.model_dump()}
    if audit_payload.get("stdin_b64"):
        audit_payload["stdin_b64"] = "<redacted>"
    audit.start(payload=audit_payload)
    try:
        result = await get_brokers().monolith.exec_in_pod(
            namespace,
            name,
            body.model_dump(),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"namespace": namespace, "name": name})
    return {"result": result, "audit_run_id": audit.run_id}


@router.get("/pods/{namespace}/{name}/archive", summary="Download a tar archive from a pod.")
async def get_pod_archive(
    namespace: str,
    name: str,
    path: str = Query(..., min_length=1),
    container: str | None = None,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.kubernetes.pod.archive.get")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    audit.target = f"{namespace}/{name}:{path}"
    audit.start(
        payload={
            "namespace": namespace,
            "name": name,
            "path": path,
            "container": container,
        }
    )
    try:
        upstream = await get_brokers().monolith.get_pod_archive(
            namespace,
            name,
            path=path,
            container=container,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"namespace": namespace, "name": name, "path": path})
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{name}-{path.strip('/') or 'root'}.tar")
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/x-tar"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/pods/{namespace}/{name}/archive", summary="Upload a tar archive to a pod.")
async def put_pod_archive(
    namespace: str,
    name: str,
    body: PodArchivePutBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.kubernetes.pod.archive.put")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = f"{namespace}/{name}:{body.path}"
    audit.start(
        payload={
            "namespace": namespace,
            "name": name,
            "path": body.path,
            "container": body.container,
            "data_b64": "<redacted>",
        }
    )
    try:
        result = await get_brokers().monolith.put_pod_archive(
            namespace,
            name,
            body.model_dump(),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"namespace": namespace, "name": name, "path": body.path})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
