"""rpi_k8s_sdk - local access SDK for the rpi_kubernetes lab."""

from .access import LocalAccessSettings, ServiceRef, load_settings, write_env_file
from .auth import ManagementAuth
from .aqp import (
    AqpControlPlaneClient,
    AqpControlPlaneError,
    AqpControlPlaneSettings,
    aqp_session,
    latest_mlflow_run,
    register_model,
    submit_backtest,
)
from .data import duckdb_engine, iceberg_table
from .datahub import DataHubClient, DataHubRecipe
from .iceberg import IcebergCatalogConfig, IcebergClient
from .minio import MinioClient, MinioObject
from .mlflow import LoggedRun, MLflowClient
from .pipelines import ArgoPipelineClient, PipelineRun
from .serving import (
    ModelArtifact,
    ModelStore,
    kserve_inferenceservice_manifest,
    vllm_deployment_manifest,
)
from .tracing import configure_tracing, get_tracer, shutdown_tracing
from .tunnels import LocalTunnelManager, PortForwardTunnel, find_free_port

__all__ = [
    "ArgoPipelineClient",
    "AqpControlPlaneClient",
    "AqpControlPlaneError",
    "AqpControlPlaneSettings",
    "DataHubClient",
    "DataHubRecipe",
    "IcebergCatalogConfig",
    "IcebergClient",
    "LocalAccessSettings",
    "LocalTunnelManager",
    "LoggedRun",
    "ManagementAuth",
    "MLflowClient",
    "MinioClient",
    "MinioObject",
    "ModelArtifact",
    "ModelStore",
    "PipelineRun",
    "PortForwardTunnel",
    "ServiceRef",
    "aqp_session",
    "configure_tracing",
    "duckdb_engine",
    "find_free_port",
    "get_tracer",
    "iceberg_table",
    "kserve_inferenceservice_manifest",
    "latest_mlflow_run",
    "load_settings",
    "register_model",
    "shutdown_tracing",
    "submit_backtest",
    "vllm_deployment_manifest",
    "write_env_file",
]
__version__ = "0.2.0"
