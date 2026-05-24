"""API routes for the management backend."""

from fastapi import APIRouter

from .alphavantage import router as alphavantage_router
from .cluster import router as cluster_router
from .deployments import router as deployments_router
from .documents import router as documents_router
from .flink import router as flink_router
from .hardware import router as hardware_router
from .health import router as health_router
from .kafka import router as kafka_router
from .mlflow import router as mlflow_router
from .observability import router as observability_router
from .redis_admin import router as redis_admin_router
from .traces import router as traces_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(cluster_router, prefix="/cluster", tags=["cluster"])
api_router.include_router(deployments_router, prefix="/deployments", tags=["deployments"])
api_router.include_router(hardware_router, prefix="/hardware", tags=["hardware"])
api_router.include_router(mlflow_router, prefix="/mlflow", tags=["mlflow"])
api_router.include_router(kafka_router, prefix="/kafka", tags=["kafka"])
api_router.include_router(flink_router, prefix="/flink", tags=["flink"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(redis_admin_router, prefix="/redis", tags=["redis"])
api_router.include_router(
    alphavantage_router, prefix="/alphavantage", tags=["alphavantage"],
)
api_router.include_router(
    observability_router, prefix="/observability", tags=["observability"],
)
api_router.include_router(traces_router, prefix="/traces", tags=["traces"])

__all__ = ["api_router"]
