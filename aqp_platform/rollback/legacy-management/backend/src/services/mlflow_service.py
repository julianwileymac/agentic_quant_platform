"""
MLFlow integration service.

Provides access to MLFlow experiment tracking data.
"""

import logging
from typing import Any, Optional

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


class MLFlowService:
    """Service for MLFlow operations."""

    def __init__(self, settings: Settings):
        """Initialize the MLFlow service."""
        self.settings = settings
        self.base_url = settings.mlflow.tracking_uri
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client for MLFlow API."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def health_check(self) -> bool:
        """Check if MLFlow server is healthy."""
        if not self.settings.mlflow.enabled:
            return False

        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"MLFlow health check failed: {e}")
            return False

    async def list_experiments(self) -> list[dict[str, Any]]:
        """List all experiments."""
        if not self.settings.mlflow.enabled:
            return []

        try:
            response = await self.client.get("/api/2.0/mlflow/experiments/search")
            response.raise_for_status()
            data = response.json()
            return data.get("experiments", [])
        except Exception as e:
            logger.error(f"Failed to list experiments: {e}")
            return []

    async def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        """Get a specific experiment by ID."""
        if not self.settings.mlflow.enabled:
            return None

        try:
            response = await self.client.get(
                "/api/2.0/mlflow/experiments/get",
                params={"experiment_id": experiment_id},
            )
            response.raise_for_status()
            return response.json().get("experiment")
        except Exception as e:
            logger.error(f"Failed to get experiment {experiment_id}: {e}")
            return None

    async def list_runs(
        self,
        experiment_ids: Optional[list[str]] = None,
        filter_string: Optional[str] = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Search for runs across experiments."""
        if not self.settings.mlflow.enabled:
            return []

        try:
            body = {
                "max_results": max_results,
            }
            if experiment_ids:
                body["experiment_ids"] = experiment_ids
            if filter_string:
                body["filter"] = filter_string

            response = await self.client.post(
                "/api/2.0/mlflow/runs/search",
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("runs", [])
        except Exception as e:
            logger.error(f"Failed to search runs: {e}")
            return []

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Get a specific run by ID."""
        if not self.settings.mlflow.enabled:
            return None

        try:
            response = await self.client.get(
                "/api/2.0/mlflow/runs/get",
                params={"run_id": run_id},
            )
            response.raise_for_status()
            return response.json().get("run")
        except Exception as e:
            logger.error(f"Failed to get run {run_id}: {e}")
            return None

    async def get_run_metrics(
        self,
        run_id: str,
        metric_keys: Optional[list[str]] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get metrics history for a run."""
        if not self.settings.mlflow.enabled:
            return {}

        try:
            run = await self.get_run(run_id)
            if not run:
                return {}

            # Get all metrics if no keys specified
            if metric_keys is None:
                metrics_data = run.get("data", {}).get("metrics", [])
                metric_keys = list({m["key"] for m in metrics_data})

            result = {}
            for key in metric_keys:
                response = await self.client.get(
                    "/api/2.0/mlflow/metrics/get-history",
                    params={"run_id": run_id, "metric_key": key},
                )
                response.raise_for_status()
                result[key] = response.json().get("metrics", [])

            return result
        except Exception as e:
            logger.error(f"Failed to get metrics for run {run_id}: {e}")
            return {}

    async def list_registered_models(self) -> list[dict[str, Any]]:
        """List all registered models."""
        if not self.settings.mlflow.enabled:
            return []

        try:
            response = await self.client.get(
                "/api/2.0/mlflow/registered-models/search",
            )
            response.raise_for_status()
            data = response.json()
            return data.get("registered_models", [])
        except Exception as e:
            logger.error(f"Failed to list registered models: {e}")
            return []

    async def get_model_versions(
        self,
        model_name: str,
    ) -> list[dict[str, Any]]:
        """Get all versions of a registered model."""
        if not self.settings.mlflow.enabled:
            return []

        try:
            response = await self.client.get(
                "/api/2.0/mlflow/registered-models/get",
                params={"name": model_name},
            )
            response.raise_for_status()
            model = response.json().get("registered_model", {})
            return model.get("latest_versions", [])
        except Exception as e:
            logger.error(f"Failed to get model versions for {model_name}: {e}")
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
