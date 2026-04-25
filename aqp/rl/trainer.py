"""Train an RL policy from a YAML recipe with MLflow autologging."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.core.registry import build_from_config

logger = logging.getLogger(__name__)


def train_from_config(cfg: dict[str, Any], run_name: str | None = None) -> dict[str, Any]:
    """Build env + agent from YAML and train with MLflow autolog."""
    import mlflow
    import mlflow.pytorch

    env_cfg = cfg.get("env")
    agent_cfg = cfg.get("agent")
    training_cfg = cfg.get("training", {}) or {}
    mlflow_cfg = cfg.get("mlflow", {}) or {}

    if not env_cfg or not agent_cfg:
        raise ValueError("Config must have 'env' and 'agent' blocks.")

    experiment = mlflow_cfg.get("experiment") or settings.mlflow_experiment
    register_as = mlflow_cfg.get("register_model_as")
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(experiment)

    env = build_from_config(env_cfg)
    agent = build_from_config(agent_cfg)

    run_name = run_name or f"{agent.algorithm.lower()}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(agent_cfg.get("kwargs", {}))
        mlflow.log_params({f"env.{k}": str(v) for k, v in env_cfg.get("kwargs", {}).items()})
        mlflow.log_params(training_cfg)

        try:
            mlflow.pytorch.autolog()
        except Exception:  # pragma: no cover
            logger.warning("mlflow.pytorch.autolog unavailable; continuing.")

        agent.build(env)
        logger.info("Training %s for %d timesteps", agent.algorithm, training_cfg.get("total_timesteps", 0))
        agent.train(total_timesteps=int(training_cfg.get("total_timesteps", 10000)))

        save_dir = Path(settings.models_dir) / run_name
        checkpoint = save_dir / "policy.zip"
        agent.save(checkpoint)
        mlflow.log_artifact(str(checkpoint))

        if register_as:
            try:
                mlflow.register_model(f"runs:/{run.info.run_id}/policy", register_as)
            except Exception:
                logger.exception("Model registry promotion failed (registry not configured?)")

        return {
            "mlflow_run_id": run.info.run_id,
            "algorithm": agent.algorithm,
            "checkpoint": str(checkpoint),
            "experiment": experiment,
        }
