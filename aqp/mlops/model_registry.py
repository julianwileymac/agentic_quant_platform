"""MLflow model registry for alpha models.

Thin helpers that wrap the MLflow Model Registry for AQP's ``IAlphaModel``
implementations. Used by :mod:`aqp.strategies.ml_alphas` to register
trained gradient-boosted models and by the Strategy Development UI to
fetch the latest production model for inference.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def register_alpha(
    name: str,
    alpha_path: str | Path,
    metrics: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    """Register (or create) an alpha model in the MLflow registry.

    Logs the artifact, transitions it to the ``Staging`` stage, and
    returns the new version string. Best-effort: returns ``None`` if
    MLflow isn't reachable.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        from aqp.mlops.mlflow_client import ensure_experiment

        ensure_experiment()
        with mlflow.start_run(run_name=f"register-{name}") as run:
            mlflow.set_tag("aqp.component", "alpha_register")
            if metrics:
                for k, v in metrics.items():
                    if isinstance(v, (int, float)):
                        try:
                            mlflow.log_metric(k, float(v))
                        except Exception:
                            continue
            if meta:
                mlflow.log_params(
                    {k: str(v)[:250] for k, v in meta.items()}
                )
            mlflow.log_artifact(str(alpha_path), artifact_path=name)
            source = f"{run.info.artifact_uri}/{name}"
            client = mlflow.MlflowClient()
            # Create the registered model if it doesn't exist.
            with contextlib.suppress(Exception):
                client.create_registered_model(name)
            version = client.create_model_version(
                name=name,
                source=source,
                run_id=run.info.run_id,
            )
            try:
                client.transition_model_version_stage(
                    name=name,
                    version=version.version,
                    stage="Staging",
                    archive_existing_versions=False,
                )
            except Exception:
                logger.debug("could not transition stage", exc_info=True)
            return str(version.version)
    except Exception:
        logger.exception("register_alpha failed for %s", name)
        return None


def load_alpha_path(name: str, stage: str = "Production") -> str | None:
    """Return the artifact path of the latest model version in ``stage``."""
    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = mlflow.MlflowClient()
        versions = client.search_model_versions(f"name='{name}'")
        for v in versions:
            if v.current_stage == stage:
                return v.source
        if versions:
            return versions[0].source
        return None
    except Exception:
        logger.exception("load_alpha_path failed for %s", name)
        return None
