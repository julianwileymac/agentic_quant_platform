"""Health check endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..services import KubernetesService, MLFlowService, MinioService
from .redis_admin import get_redis_service

router = APIRouter()


class HealthStatus(BaseModel):
    """Health status response."""

    status: str
    version: str
    kubernetes_connected: bool
    mlflow_connected: bool
    minio_connected: bool
    redis_connected: bool = False
    redis_modules_missing: list[str] = []


@router.get("/health", response_model=HealthStatus)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthStatus:
    """Check service health and dependencies."""
    # Check Kubernetes connection
    k8s_connected = False
    try:
        k8s_service = KubernetesService(settings)
        await k8s_service.get_namespaces()
        k8s_connected = True
    except Exception:
        pass

    # Check MLFlow connection
    mlflow_connected = False
    if settings.mlflow.enabled:
        try:
            mlflow_service = MLFlowService(settings)
            mlflow_connected = await mlflow_service.health_check()
        except Exception:
            pass

    # Check MinIO connection
    minio_connected = False
    if settings.minio.enabled:
        try:
            minio_service = MinioService(settings)
            minio_connected = await minio_service.health_check()
        except Exception:
            pass

    # Check Redis connection (document store + cache backbone)
    redis_connected = False
    missing_modules: list[str] = []
    if settings.redis.enabled:
        try:
            redis_service = get_redis_service(settings)
            state = await redis_service.health()
            redis_connected = bool(state.get("ping"))
            missing_modules = list(state.get("missing_modules") or [])
        except Exception:
            pass

    return HealthStatus(
        status="healthy" if k8s_connected else "degraded",
        version="0.1.0",
        kubernetes_connected=k8s_connected,
        mlflow_connected=mlflow_connected,
        minio_connected=minio_connected,
        redis_connected=redis_connected,
        redis_modules_missing=missing_modules,
    )


@router.get("/ready")
async def readiness_check() -> dict:
    """Kubernetes readiness probe."""
    return {"ready": True}


@router.get("/live")
async def liveness_check() -> dict:
    """Kubernetes liveness probe."""
    return {"live": True}
