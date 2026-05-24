"""Deployment management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings
from ..models.deployments import (
    DeploymentConfig,
    DeploymentInfo,
    RollbackRequest,
    ScaleRequest,
)
from ..services import DeploymentService, KubernetesService

router = APIRouter()


def get_deployment_service(
    settings: Settings = Depends(get_settings),
) -> DeploymentService:
    """Get deployment service instance."""
    k8s = KubernetesService(settings)
    return DeploymentService(settings, k8s)


@router.get("", response_model=list[DeploymentInfo])
async def list_deployments(
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    service: DeploymentService = Depends(get_deployment_service),
) -> list[DeploymentInfo]:
    """List all deployments."""
    try:
        return await service.list_deployments(namespace=namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{namespace}/{name}", response_model=DeploymentInfo)
async def get_deployment(
    namespace: str,
    name: str,
    service: DeploymentService = Depends(get_deployment_service),
) -> DeploymentInfo:
    """Get a specific deployment."""
    try:
        deployment = await service.get_deployment(name, namespace)
        if not deployment:
            raise HTTPException(
                status_code=404,
                detail=f"Deployment {name} not found in {namespace}",
            )
        return deployment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=DeploymentInfo, status_code=201)
async def create_deployment(
    config: DeploymentConfig,
    service: DeploymentService = Depends(get_deployment_service),
) -> DeploymentInfo:
    """Create a new deployment."""
    try:
        return await service.create_deployment(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{namespace}/{name}/scale", response_model=DeploymentInfo)
async def scale_deployment(
    namespace: str,
    name: str,
    request: ScaleRequest,
    service: DeploymentService = Depends(get_deployment_service),
) -> DeploymentInfo:
    """Scale a deployment."""
    try:
        return await service.scale_deployment(name, namespace, request.replicas)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{namespace}/{name}/restart", response_model=DeploymentInfo)
async def restart_deployment(
    namespace: str,
    name: str,
    service: DeploymentService = Depends(get_deployment_service),
) -> DeploymentInfo:
    """Restart a deployment (rolling restart)."""
    try:
        return await service.restart_deployment(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{namespace}/{name}/rollback", response_model=DeploymentInfo)
async def rollback_deployment(
    namespace: str,
    name: str,
    request: RollbackRequest,
    service: DeploymentService = Depends(get_deployment_service),
) -> DeploymentInfo:
    """Rollback a deployment to a previous revision."""
    try:
        return await service.rollback_deployment(name, namespace, request.revision)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{namespace}/{name}", status_code=204)
async def delete_deployment(
    namespace: str,
    name: str,
    delete_service: bool = Query(True, description="Also delete associated service"),
    service: DeploymentService = Depends(get_deployment_service),
) -> None:
    """Delete a deployment."""
    try:
        deleted = await service.delete_deployment(name, namespace, delete_service)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Deployment {name} not found in {namespace}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
