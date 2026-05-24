"""MLFlow integration API endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings
from ..services import MLFlowService

router = APIRouter()


def get_mlflow_service(
    settings: Settings = Depends(get_settings),
) -> MLFlowService:
    """Get MLFlow service instance."""
    return MLFlowService(settings)


@router.get("/health")
async def mlflow_health(
    service: MLFlowService = Depends(get_mlflow_service),
) -> dict:
    """Check MLFlow server health."""
    healthy = await service.health_check()
    return {"healthy": healthy}


@router.get("/experiments", response_model=list[dict[str, Any]])
async def list_experiments(
    service: MLFlowService = Depends(get_mlflow_service),
) -> list[dict[str, Any]]:
    """List all MLFlow experiments."""
    try:
        return await service.list_experiments()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    service: MLFlowService = Depends(get_mlflow_service),
) -> dict[str, Any]:
    """Get a specific experiment."""
    try:
        experiment = await service.get_experiment(experiment_id)
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment {experiment_id} not found",
            )
        return experiment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=list[dict[str, Any]])
async def list_runs(
    experiment_ids: Optional[str] = Query(
        None,
        description="Comma-separated experiment IDs",
    ),
    filter_string: Optional[str] = Query(
        None,
        description="MLFlow filter string",
    ),
    max_results: int = Query(100, ge=1, le=1000),
    service: MLFlowService = Depends(get_mlflow_service),
) -> list[dict[str, Any]]:
    """Search for runs."""
    try:
        exp_ids = experiment_ids.split(",") if experiment_ids else None
        return await service.list_runs(
            experiment_ids=exp_ids,
            filter_string=filter_string,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    service: MLFlowService = Depends(get_mlflow_service),
) -> dict[str, Any]:
    """Get a specific run."""
    try:
        run = await service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(
    run_id: str,
    metric_keys: Optional[str] = Query(
        None,
        description="Comma-separated metric keys",
    ),
    service: MLFlowService = Depends(get_mlflow_service),
) -> dict[str, list[dict[str, Any]]]:
    """Get metrics history for a run."""
    try:
        keys = metric_keys.split(",") if metric_keys else None
        return await service.get_run_metrics(run_id, metric_keys=keys)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", response_model=list[dict[str, Any]])
async def list_registered_models(
    service: MLFlowService = Depends(get_mlflow_service),
) -> list[dict[str, Any]]:
    """List all registered models."""
    try:
        return await service.list_registered_models()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_name}/versions", response_model=list[dict[str, Any]])
async def get_model_versions(
    model_name: str,
    service: MLFlowService = Depends(get_mlflow_service),
) -> list[dict[str, Any]]:
    """Get all versions of a registered model."""
    try:
        return await service.get_model_versions(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
