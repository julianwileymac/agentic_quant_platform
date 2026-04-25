"""Model registry helpers — promote MLflow model versions across stages."""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.persistence.db import get_session
from aqp.persistence.models import ModelVersion

logger = logging.getLogger(__name__)


def promote(
    name: str,
    version: str,
    stage: str = "Staging",
    dataset_hash: str | None = None,
    metrics: dict[str, Any] | None = None,
    algo: str | None = None,
) -> str:
    """Transition an MLflow model version and mirror it in Postgres."""
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = mlflow.MlflowClient()
    try:
        client.transition_model_version_stage(name=name, version=version, stage=stage)
    except Exception:  # pragma: no cover
        logger.exception("MLflow stage transition failed")

    row = ModelVersion(
        registry_name=name,
        mlflow_version=str(version),
        stage=stage,
        dataset_hash=dataset_hash,
        algo=algo,
        metrics=metrics or {},
    )
    with get_session() as session:
        session.add(row)
        session.flush()
        return row.id


def latest_stage(name: str, stage: str = "Production") -> dict[str, Any] | None:
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = mlflow.MlflowClient()
    versions = client.search_model_versions(f"name='{name}'")
    for v in versions:
        if v.current_stage == stage:
            return {
                "name": v.name,
                "version": v.version,
                "stage": v.current_stage,
                "run_id": v.run_id,
                "source": v.source,
            }
    return None
