"""``/streaming/flink`` REST surface.

Native Flink admin via :mod:`aqp.streaming.admin.flink_admin` (REST
+ kubernetes client wrapper for ``FlinkSessionJob`` CRUD). Falls back
to the cluster-mgmt proxy when the kubernetes client / Flink REST
URL aren't configured.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.streaming.admin import (
    FlinkAdminError,
    FlinkAdminUnavailableError,
    get_flink_rest_client,
    get_flink_session_jobs,
)
from aqp.streaming.runtime import submit_factor_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming/flink", tags=["streaming"])


class FlinkSessionJobView(BaseModel):
    name: str
    namespace: str
    state: str | None = None
    parallelism: int | None = None
    job_id: str | None = None
    jar_uri: str | None = None
    entry_class: str | None = None
    args: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class FlinkJobOverviewView(BaseModel):
    jid: str
    name: str
    state: str
    start_time: int | None = None
    end_time: int | None = None
    duration: int | None = None
    tasks: dict[str, int] = Field(default_factory=dict)


class FlinkSessionJobCreateRequest(BaseModel):
    body: dict[str, Any]


class FlinkSessionJobPatchRequest(BaseModel):
    patch: dict[str, Any]


class FlinkFactorExportRequest(BaseModel):
    name: str
    factor_expression: str | None = None
    pipeline_export: dict[str, Any] | None = None
    namespace: str | None = None
    jar_uri: str | None = None
    entry_class: str | None = None
    args: list[str] = Field(default_factory=list)
    parallelism: int = 1


def _native_or_proxy_flink(operation: str):
    """Try the native session-job client first, fall back to cluster-mgmt."""
    try:
        return ("native", get_flink_session_jobs())
    except FlinkAdminUnavailableError as exc:
        logger.debug("flink native unavailable for %s: %s", operation, exc)
    except FlinkAdminError as exc:
        logger.debug("flink native error for %s: %s", operation, exc)
    try:
        from aqp.services.cluster_mgmt_client import get_cluster_mgmt_client

        return ("proxy", get_cluster_mgmt_client())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"flink admin unavailable (native+proxy): {exc}",
        ) from exc


@router.get("/sessionjobs", response_model=list[FlinkSessionJobView])
def list_session_jobs(namespace: str | None = None) -> list[FlinkSessionJobView]:
    backend, client = _native_or_proxy_flink("list_session_jobs")
    try:
        if backend == "native":
            return [FlinkSessionJobView(**j.to_dict()) for j in client.list(namespace=namespace)]
        return [FlinkSessionJobView(**r) for r in client.flink_session_jobs(namespace=namespace)]
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessionjobs", response_model=FlinkSessionJobView, status_code=201)
def create_session_job(req: FlinkSessionJobCreateRequest) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("create_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(**client.create(req.body).to_dict())
        return FlinkSessionJobView(**client.flink_create_session_job(req.body))
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessionjobs/{name}", response_model=FlinkSessionJobView)
def get_session_job(name: str, namespace: str | None = None) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("get_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(**client.get(name, namespace=namespace).to_dict())
        return FlinkSessionJobView(**client.flink_session_job(name, namespace=namespace))
    except FlinkAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/sessionjobs/{name}", response_model=FlinkSessionJobView)
def patch_session_job(
    name: str,
    req: FlinkSessionJobPatchRequest,
    namespace: str | None = None,
) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("patch_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(
                **client.patch(name, req.patch, namespace=namespace).to_dict()
            )
        return FlinkSessionJobView(
            **client.flink_patch_session_job(name, req.patch, namespace=namespace)
        )
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/sessionjobs/{name}", status_code=204, response_class=Response)
def delete_session_job(name: str, namespace: str | None = None) -> Response:
    backend, client = _native_or_proxy_flink("delete_session_job")
    try:
        if backend == "native":
            client.delete(name, namespace=namespace)
        else:
            client.flink_delete_session_job(name, namespace=namespace)
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/sessionjobs/{name}/activate", response_model=FlinkSessionJobView)
def activate_session_job(name: str, namespace: str | None = None) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("activate_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(
                **client.set_state(name, "running", namespace=namespace).to_dict()
            )
        return FlinkSessionJobView(**client.flink_activate_session_job(name, namespace=namespace))
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessionjobs/{name}/suspend", response_model=FlinkSessionJobView)
def suspend_session_job(name: str, namespace: str | None = None) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("suspend_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(
                **client.set_state(name, "suspended", namespace=namespace).to_dict()
            )
        return FlinkSessionJobView(**client.flink_suspend_session_job(name, namespace=namespace))
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessionjobs/{name}/scale", response_model=FlinkSessionJobView)
def scale_session_job(name: str, parallelism: int, namespace: str | None = None) -> FlinkSessionJobView:
    backend, client = _native_or_proxy_flink("scale_session_job")
    try:
        if backend == "native":
            return FlinkSessionJobView(
                **client.scale(name, parallelism, namespace=namespace).to_dict()
            )
        return FlinkSessionJobView(
            **client.flink_scale_session_job(name, parallelism=parallelism, namespace=namespace)
        )
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessionjobs/{name}/savepoint")
def trigger_session_job_savepoint(name: str) -> dict[str, Any]:
    try:
        rest = get_flink_rest_client()
        sessions = get_flink_session_jobs()
        sj = sessions.get(name)
        if not sj.job_id:
            raise HTTPException(status_code=404, detail=f"session job {name} has no active jobId")
        return rest.trigger_savepoint(sj.job_id)
    except FlinkAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[FlinkJobOverviewView])
def jobs_overview() -> list[FlinkJobOverviewView]:
    try:
        rest = get_flink_rest_client()
        return [FlinkJobOverviewView(**j.to_dict()) for j in rest.jobs_overview()]
    except FlinkAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def job_detail(job_id: str) -> dict[str, Any]:
    try:
        rest = get_flink_rest_client()
        return rest.job_detail(job_id)
    except FlinkAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FlinkAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/exceptions")
def job_exceptions(job_id: str) -> dict[str, Any]:
    try:
        rest = get_flink_rest_client()
        return rest.job_exceptions(job_id)
    except FlinkAdminUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FlinkAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/jobs/factor-export")
def factor_export(req: FlinkFactorExportRequest) -> dict[str, Any]:
    """Render + apply a FlinkSessionJob for an AQP factor / ML pipeline."""
    return submit_factor_job(
        name=req.name,
        factor_expression=req.factor_expression,
        pipeline_export=req.pipeline_export,
        namespace=req.namespace,
        jar_uri=req.jar_uri,
        entry_class=req.entry_class,
        args=req.args,
        parallelism=req.parallelism,
    )


__all__ = ["router"]
