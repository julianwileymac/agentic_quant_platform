"""Flink management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models.flink import (
    FlinkDeploymentInfo,
    FlinkJobState,
    FlinkMetrics,
    FlinkSessionJobCreate,
    FlinkSessionJobInfo,
    FlinkSessionJobPatch,
)
from ..services import FlinkService, KubernetesService

router = APIRouter()


def get_flink_service(settings: Settings = Depends(get_settings)) -> FlinkService:
    k8s = KubernetesService(settings)
    return FlinkService(settings, k8s)


@router.get("/deployments", response_model=list[FlinkDeploymentInfo])
async def list_deployments(service: FlinkService = Depends(get_flink_service)):
    return await service.list_deployments()


@router.get("/sessionjobs", response_model=list[FlinkSessionJobInfo])
async def list_session_jobs(service: FlinkService = Depends(get_flink_service)):
    return await service.list_session_jobs()


@router.get("/sessionjobs/{name}", response_model=FlinkSessionJobInfo)
async def get_session_job(name: str, service: FlinkService = Depends(get_flink_service)):
    job = await service.get_session_job(name)
    if job is None:
        raise HTTPException(status_code=404, detail=f"FlinkSessionJob {name} not found")
    return job


@router.post("/sessionjobs", response_model=FlinkSessionJobInfo, status_code=201)
async def create_session_job(
    payload: FlinkSessionJobCreate,
    service: FlinkService = Depends(get_flink_service),
):
    try:
        return await service.create_session_job(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/sessionjobs/{name}", response_model=FlinkSessionJobInfo)
async def patch_session_job(
    name: str,
    payload: FlinkSessionJobPatch,
    service: FlinkService = Depends(get_flink_service),
):
    try:
        return await service.patch_session_job(name, payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sessionjobs/{name}/activate", response_model=FlinkSessionJobInfo)
async def activate_session_job(name: str, service: FlinkService = Depends(get_flink_service)):
    return await service.patch_session_job(
        name,
        FlinkSessionJobPatch(state=FlinkJobState.RUNNING),
    )


@router.post("/sessionjobs/{name}/suspend", response_model=FlinkSessionJobInfo)
async def suspend_session_job(name: str, service: FlinkService = Depends(get_flink_service)):
    return await service.patch_session_job(
        name,
        FlinkSessionJobPatch(state=FlinkJobState.SUSPENDED),
    )


@router.post("/sessionjobs/{name}/savepoint", response_model=FlinkSessionJobInfo)
async def trigger_savepoint(name: str, service: FlinkService = Depends(get_flink_service)):
    return await service.patch_session_job(
        name,
        FlinkSessionJobPatch(savepoint_trigger=True),
    )


@router.post("/sessionjobs/{name}/scale", response_model=FlinkSessionJobInfo)
async def scale_session_job(
    name: str,
    parallelism: int,
    service: FlinkService = Depends(get_flink_service),
):
    return await service.patch_session_job(
        name,
        FlinkSessionJobPatch(parallelism=parallelism),
    )


@router.delete("/sessionjobs/{name}", status_code=204)
async def delete_session_job(name: str, service: FlinkService = Depends(get_flink_service)):
    await service.delete_session_job(name)


@router.get("/jobs", response_model=list[FlinkMetrics])
async def list_rest_jobs(service: FlinkService = Depends(get_flink_service)):
    return await service.list_rest_jobs()


@router.get("/jobs/{job_id}", response_model=FlinkMetrics)
async def get_job_metrics(job_id: str, service: FlinkService = Depends(get_flink_service)):
    try:
        return await service.get_job_metrics(job_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
