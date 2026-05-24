"""Local access profiles for the rpi_kubernetes lab."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: str) -> int:
    try:
        return int(_env(name, default))
    except ValueError:
        return int(default)


def _env_bool(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


def _normalize_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


@dataclass(frozen=True, slots=True)
class ServiceRef:
    """A Kubernetes service that can be exposed through a local tunnel."""

    name: str
    namespace: str
    port: int
    local_port: int
    scheme: str = "http"

    @property
    def local_url(self) -> str:
        return f"{self.scheme}://127.0.0.1:{self.local_port}"


@dataclass(frozen=True, slots=True)
class LocalAccessSettings:
    """Environment-backed connection profile for notebooks and local apps."""

    profile: str = field(default_factory=lambda: _env("RPI_K8S_PROFILE", "local"))
    kubeconfig: str = field(default_factory=lambda: _env("KUBECONFIG", ""))
    kube_context: str = field(default_factory=lambda: _env("RPI_K8S_CONTEXT", ""))
    namespace_data: str = field(default_factory=lambda: _env("RPI_K8S_DATA_NAMESPACE", "data-services"))
    namespace_ml: str = field(default_factory=lambda: _env("RPI_K8S_ML_NAMESPACE", "ml-platform"))
    namespace_mlops: str = field(default_factory=lambda: _env("RPI_K8S_MLOPS_NAMESPACE", "mlops"))
    namespace_observability: str = field(
        default_factory=lambda: _env("RPI_K8S_OBSERVABILITY_NAMESPACE", "observability")
    )
    minio_endpoint: str = field(default_factory=lambda: _normalize_url(_env("MINIO_ENDPOINT", "http://s3.local")))
    minio_access_key: str = field(default_factory=lambda: _env("MINIO_ACCESS_KEY", "minioadmin"))
    minio_secret_key: str = field(default_factory=lambda: _env("MINIO_SECRET_KEY", "minioadmin123"))
    minio_region: str = field(default_factory=lambda: _env("MINIO_REGION", "us-east-1"))
    mlflow_tracking_uri: str = field(
        default_factory=lambda: _normalize_url(_env("MLFLOW_TRACKING_URI", "http://mlflow.local"))
    )
    datahub_frontend_url: str = field(
        default_factory=lambda: _normalize_url(_env("DATAHUB_FRONTEND_URL", "http://datahub.local"))
    )
    datahub_gms_url: str = field(
        default_factory=lambda: _normalize_url(_env("DATAHUB_GMS_URL", "http://127.0.0.1:8080"))
    )
    datahub_token: str = field(default_factory=lambda: _env("DATAHUB_TOKEN", ""))
    iceberg_catalog_uri: str = field(
        default_factory=lambda: _env("ICEBERG_CATALOG_URI", "http://127.0.0.1:8080/iceberg")
    )
    iceberg_warehouse: str = field(default_factory=lambda: _env("ICEBERG_WAREHOUSE", "s3://iceberg-warehouse/"))
    otlp_endpoint: str = field(
        default_factory=lambda: _normalize_url(_env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317"))
    )
    argo_server_url: str = field(
        default_factory=lambda: _normalize_url(_env("ARGO_SERVER_URL", "http://argo.local"))
    )
    model_bucket: str = field(default_factory=lambda: _env("RPI_K8S_MODEL_BUCKET", "model-registry"))
    serving_profile: str = field(default_factory=lambda: _env("RPI_K8S_SERVING_PROFILE", "cpu-small"))
    auto_tunnel: bool = field(default_factory=lambda: _env_bool("RPI_K8S_AUTO_TUNNEL", "true"))

    @property
    def datahub_gms(self) -> ServiceRef:
        return ServiceRef(
            name="datahub-datahub-gms",
            namespace=self.namespace_data,
            port=8080,
            local_port=_env_int("DATAHUB_GMS_LOCAL_PORT", "8080"),
        )

    @property
    def otel_collector(self) -> ServiceRef:
        return ServiceRef(
            name="otel-collector",
            namespace=self.namespace_observability,
            port=4317,
            local_port=_env_int("OTEL_COLLECTOR_LOCAL_PORT", "4317"),
        )

    @property
    def argo_server(self) -> ServiceRef:
        return ServiceRef(
            name="argo-workflows-server",
            namespace=self.namespace_mlops,
            port=2746,
            local_port=_env_int("ARGO_SERVER_LOCAL_PORT", "2746"),
        )

    @property
    def mlflow(self) -> ServiceRef:
        return ServiceRef(
            name="mlflow",
            namespace=self.namespace_ml,
            port=5000,
            local_port=_env_int("MLFLOW_LOCAL_PORT", "5000"),
        )

    @property
    def minio(self) -> ServiceRef:
        return ServiceRef(
            name="minio",
            namespace=self.namespace_data,
            port=9000,
            local_port=_env_int("MINIO_LOCAL_PORT", "9000"),
        )

    @property
    def postgresql(self) -> ServiceRef:
        return ServiceRef(
            name="postgresql",
            namespace=self.namespace_data,
            port=5432,
            local_port=_env_int("POSTGRES_LOCAL_PORT", "5432"),
        )

    @property
    def redis(self) -> ServiceRef:
        return ServiceRef(
            name="redis",
            namespace=self.namespace_data,
            port=6379,
            local_port=_env_int("REDIS_LOCAL_PORT", "6379"),
        )

    @property
    def jaeger_query(self) -> ServiceRef:
        return ServiceRef(
            name="jaeger-query",
            namespace=self.namespace_observability,
            port=16686,
            local_port=_env_int("JAEGER_LOCAL_PORT", "16686"),
        )

    @property
    def grafana(self) -> ServiceRef:
        return ServiceRef(
            name="prometheus-grafana",
            namespace=self.namespace_observability,
            port=80,
            local_port=_env_int("GRAFANA_LOCAL_PORT", "3000"),
        )

    def to_env(self) -> dict[str, str]:
        """Return a local shell profile without exposing unset optional tokens."""

        values = {
            "RPI_K8S_PROFILE": self.profile,
            "RPI_K8S_CONTEXT": self.kube_context,
            "MINIO_ENDPOINT": self.minio_endpoint,
            "MINIO_ACCESS_KEY": self.minio_access_key,
            "MINIO_REGION": self.minio_region,
            "MLFLOW_TRACKING_URI": self.mlflow_tracking_uri,
            "DATAHUB_FRONTEND_URL": self.datahub_frontend_url,
            "DATAHUB_GMS_URL": self.datahub_gms_url,
            "ICEBERG_CATALOG_URI": self.iceberg_catalog_uri,
            "ICEBERG_WAREHOUSE": self.iceberg_warehouse,
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.otlp_endpoint,
            "ARGO_SERVER_URL": self.argo_server_url,
            "RPI_K8S_MODEL_BUCKET": self.model_bucket,
            "RPI_K8S_SERVING_PROFILE": self.serving_profile,
        }
        if self.kubeconfig:
            values["KUBECONFIG"] = self.kubeconfig
        if self.minio_secret_key:
            values["MINIO_SECRET_KEY"] = self.minio_secret_key
        if self.datahub_token:
            values["DATAHUB_TOKEN"] = self.datahub_token
        return values


def load_settings() -> LocalAccessSettings:
    return LocalAccessSettings()


def write_env_file(path: str | Path, settings: LocalAccessSettings | None = None) -> Path:
    """Write a dotenv-style profile for local notebooks and scripts."""

    target = Path(path)
    active = settings or load_settings()
    lines = [f"{key}={value}" for key, value in sorted(active.to_env().items())]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
