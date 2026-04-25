"""MLOps layer: MLflow client, model registry, dataset lineage, serving
adapters (MLflow Serve / Ray Serve / TorchServe), cross-repo lineage
bridge, and Prometheus metrics."""

from aqp.mlops.lineage import hash_dataframe, hash_file, hash_parquet_dir
from aqp.mlops.lineage_bridge import (
    LineageEvent,
    emit_dataset,
    emit_model,
    emit_run,
    emit_serve_deployment,
    emit_strategy_version,
)
from aqp.mlops.metrics import (
    BACKTEST_DURATION,
    BACKTEST_SHARPE,
    PAPER_PNL,
    SERVE_LATENCY,
    SERVE_REQUESTS,
    TRAIN_DURATION,
    time_histogram,
)
from aqp.mlops.mlflow_client import (
    ensure_experiment,
    log_backtest,
    promote_to_production,
    register_and_serve,
)
from aqp.mlops.registry import latest_stage, promote
from aqp.mlops.serving import DeploymentInfo, ModelDeployment, PreparedModel

__all__ = [
    "BACKTEST_DURATION",
    "BACKTEST_SHARPE",
    "DeploymentInfo",
    "LineageEvent",
    "ModelDeployment",
    "PAPER_PNL",
    "PreparedModel",
    "SERVE_LATENCY",
    "SERVE_REQUESTS",
    "TRAIN_DURATION",
    "emit_dataset",
    "emit_model",
    "emit_run",
    "emit_serve_deployment",
    "emit_strategy_version",
    "ensure_experiment",
    "hash_dataframe",
    "hash_file",
    "hash_parquet_dir",
    "latest_stage",
    "log_backtest",
    "promote",
    "promote_to_production",
    "register_and_serve",
    "time_histogram",
]
