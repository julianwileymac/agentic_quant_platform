"""MLflow helpers for local tracking and model registry workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .access import LocalAccessSettings, load_settings


@dataclass(slots=True)
class LoggedRun:
    experiment_name: str
    run_id: str
    tracking_uri: str


class MLflowClient:
    """Thin wrapper around the MLflow SDK with lab defaults."""

    def __init__(self, settings: LocalAccessSettings | None = None):
        self.settings = settings or load_settings()

    def _mlflow(self) -> Any:
        try:
            import mlflow
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Install rpi_k8s_sdk[mlflow] to use MLflow helpers") from exc
        mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
        return mlflow

    def ensure_experiment(self, name: str) -> str:
        mlflow = self._mlflow()
        experiment = mlflow.get_experiment_by_name(name)
        if experiment:
            return experiment.experiment_id
        return mlflow.create_experiment(name)

    def log_artifacts(
        self,
        experiment_name: str,
        artifact_path: str | Path,
        *,
        run_name: str | None = None,
        params: dict[str, Any] | None = None,
        metrics: dict[str, float] | None = None,
    ) -> LoggedRun:
        mlflow = self._mlflow()
        self.ensure_experiment(experiment_name)
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=run_name) as run:
            if params:
                mlflow.log_params(params)
            if metrics:
                mlflow.log_metrics(metrics)
            path = Path(artifact_path)
            if path.is_dir():
                mlflow.log_artifacts(str(path))
            else:
                mlflow.log_artifact(str(path))
            return LoggedRun(
                experiment_name=experiment_name,
                run_id=run.info.run_id,
                tracking_uri=self.settings.mlflow_tracking_uri,
            )

    def register_model(self, model_uri: str, name: str) -> Any:
        mlflow = self._mlflow()
        return mlflow.register_model(model_uri=model_uri, name=name)

    def list_runs(
        self,
        *,
        experiment_name: str,
        max_results: int = 25,
        order_by: list[str] | None = None,
    ) -> list[LoggedRun]:
        """Return recent runs under an experiment ordered by start time desc."""

        mlflow = self._mlflow()
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            return []
        order_by = order_by or ["attributes.start_time DESC"]
        runs = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            max_results=max_results,
            order_by=order_by,
            output_format="list",
        )
        return [
            LoggedRun(
                experiment_name=experiment_name,
                run_id=run.info.run_id,
                tracking_uri=self.settings.mlflow_tracking_uri,
            )
            for run in runs
        ]
