"""
Configuration management using Pydantic Settings.

Environment variables can override all settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KubernetesSettings(BaseSettings):
    """Kubernetes connection settings."""

    model_config = SettingsConfigDict(env_prefix="K8S_")

    kubeconfig_path: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file. If None, uses in-cluster config.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Kubernetes context to use. If None, uses current context.",
    )
    namespace: str = Field(
        default="default",
        description="Default namespace for operations.",
    )
    auto_discover: bool = Field(
        default=True,
        description="Auto-discover local clusters (in-cluster, env KUBECONFIG, default kubeconfig).",
    )
    extra_kubeconfig_paths: list[str] = Field(
        default=[],
        description="Additional kubeconfig paths to try during auto-discovery.",
    )
    context_preference: list[str] = Field(
        default=[],
        description="Preferred contexts to try (in order) when auto-detecting.",
    )


class TelemetrySettings(BaseSettings):
    """OpenTelemetry settings."""

    model_config = SettingsConfigDict(env_prefix="OTEL_")

    enabled: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    service_name: str = Field(default="rpi-k8s-management", description="Service name for traces")
    exporter_endpoint: str = Field(
        default="http://otel-collector.observability:4317",
        description="OTLP exporter endpoint",
    )


class MLFlowSettings(BaseSettings):
    """MLFlow settings."""

    model_config = SettingsConfigDict(env_prefix="MLFLOW_")

    enabled: bool = Field(default=True, description="Enable MLFlow integration")
    tracking_uri: str = Field(
        default="http://mlflow.ml-platform:5000",
        description="MLFlow tracking server URI",
    )


class MinioSettings(BaseSettings):
    """MinIO settings."""

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    enabled: bool = Field(default=True, description="Enable MinIO health checks")
    endpoint: str = Field(
        default="http://minio.data-services.svc.cluster.local:9000",
        description="MinIO API endpoint",
    )
    health_path: str = Field(
        default="/minio/health/ready",
        description="MinIO health check path",
    )
    timeout_seconds: float = Field(
        default=5.0,
        description="Health check timeout in seconds",
    )


class HardwareSettings(BaseSettings):
    """Hardware monitoring settings."""

    model_config = SettingsConfigDict(env_prefix="HARDWARE_")

    ssh_user: str = Field(default="pi", description="SSH username for RPi nodes")
    ssh_key_path: Optional[str] = Field(
        default=None,
        description="Path to SSH private key",
    )
    ssh_timeout: int = Field(default=10, description="SSH connection timeout in seconds")
    metrics_interval: int = Field(
        default=30,
        description="Interval for collecting hardware metrics (seconds)",
    )


class KafkaSettings(BaseSettings):
    """Kafka (Strimzi) settings."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_")

    enabled: bool = Field(default=True)
    namespace: str = Field(
        default="data-services",
        description="Namespace hosting the Strimzi Kafka cluster.",
    )
    cluster_name: str = Field(default="trading-kafka")
    bootstrap_plain: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092"
    )
    bootstrap_scram: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094"
    )
    bridge_url: str = Field(
        default="http://trading-bridge-bridge-service.data-services.svc.cluster.local:8080"
    )
    schema_registry_url: str = Field(
        default="http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"
    )


class FlinkSettings(BaseSettings):
    """Flink settings (session cluster + jobs)."""

    model_config = SettingsConfigDict(env_prefix="FLINK_")

    enabled: bool = Field(default=True)
    namespace: str = Field(default="flink")
    session_cluster: str = Field(default="flink-trading-session")
    rest_url: str = Field(
        default="http://flink-trading-session-rest.flink.svc.cluster.local:8081"
    )


class RedisSettings(BaseSettings):
    """Shared Redis 8 Stack connection for cache, vectors, agent memory."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    enabled: bool = Field(default=True, description="Enable Redis-backed caching + document store")
    url: str = Field(
        default="redis://:ragflow123@redis.data-services.svc.cluster.local:6379/0",
        description="Redis connection URL used by the management API and shared with pipelines.",
    )
    host: str = Field(default="redis.data-services.svc.cluster.local")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: str = Field(default="ragflow123")
    index_prefix: str = Field(
        default="rpi",
        description="RediSearch key prefix (keeps tenants isolated on a shared instance).",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Default TTL for the cache-aside decorator.",
    )
    semantic_cache_threshold: float = Field(
        default=0.15,
        description="Cosine distance threshold for SemanticCache hits.",
    )
    health_timeout_seconds: float = Field(default=3.0)
    tls_enabled: bool = Field(default=False)


class AlphaVantageSettings(BaseSettings):
    """Alpha Vantage integration (polling-only REST data provider).

    The API key is loaded by the custom client engine with this resolution
    order: explicit kwarg -> ``ALPHAVANTAGE_API_KEY`` env -> the file pointed to by
    ``api_key_file`` (or ``ALPHAVANTAGE_API_KEY_FILE``) -> the k8s mount path.
    """

    model_config = SettingsConfigDict(env_prefix="ALPHAVANTAGE_")

    enabled: bool = Field(default=True, description="Enable Alpha Vantage endpoints")
    api_key: Optional[str] = Field(
        default=None,
        description="Inline API key override (not recommended for production).",
    )
    api_key_file: Optional[str] = Field(
        default=r"C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt",
        description="Local path to an AV API token file. Windows default for dev.",
    )
    k8s_key_mount: str = Field(
        default="/var/run/secrets/alphavantage/api-key",
        description="In-cluster secret mount consumed by the credentials loader.",
    )
    base_url: str = Field(default="https://www.alphavantage.co/query")
    rpm_limit: int = Field(default=75, description="Requests per minute budget.")
    daily_limit: int = Field(
        default=0,
        description="Daily request cap (0 = unlimited / premium).",
    )
    timeout_seconds: float = Field(default=15.0)
    max_retries: int = Field(default=5)
    cache_backend: str = Field(
        default="memory",
        description="Cache backend: memory|redis|sqlite|none",
    )
    cache_max_entries: int = Field(default=1024)
    cache_sqlite_path: Optional[str] = Field(default=None)
    rapidapi: bool = Field(default=False)
    producer_namespace: str = Field(
        default="data-services",
        description="Namespace hosting the AV streaming producer Deployment.",
    )
    producer_deployment: str = Field(
        default="alphavantage-producer",
        description="Deployment name toggled by the /api/alphavantage/stream endpoints.",
    )
    bulk_workflow_namespace: str = Field(
        default="mlops",
        description="Namespace where the AV Argo WorkflowTemplates live.",
    )
    bulk_workflow_service_account: str = Field(default="argo-workflow")


class DocumentStoreSettings(BaseSettings):
    """Configuration for the self-service document store portal."""

    model_config = SettingsConfigDict(env_prefix="DOCSTORE_")

    enabled: bool = Field(default=True)
    bucket: str = Field(
        default="dagster-artifacts",
        description="MinIO bucket that backs uploaded document blobs.",
    )
    bucket_prefix: str = Field(
        default="documents/",
        description="Prefix inside the bucket for uploaded documents.",
    )
    artifact_buckets: list[str] = Field(
        default=["dagster-artifacts", "mlflow-artifacts", "pipeline-raw", "pipeline-processed"],
        description="Buckets exposed by the ad-hoc JSON artifact browser.",
    )
    max_upload_mb: int = Field(default=50)
    chunk_size: int = Field(default=800)
    chunk_overlap: int = Field(default=100)
    embedding_dim: int = Field(default=16, description="Fallback dim if EMBEDDING_* env is unset.")
    embedding_model: str = Field(default="deterministic")
    allowed_mime_types: list[str] = Field(
        default=[
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
            "application/pdf",
            "application/octet-stream",
        ]
    )
    default_collection: str = Field(default="general")
    vector_index_name: str = Field(default="idx:chunks")
    document_index_name: str = Field(default="idx:documents")
    annotation_index_name: str = Field(default="idx:annotations")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    cors_origins: list[str] = Field(
        default=["*"],
        description=(
            "Allowed CORS origins. Defaults to '*' for backwards compat "
            "with local dev; production deployments should set "
            "``APP_CORS_ORIGINS=https://...`` to lock down the allowlist."
        ),
    )

    # --- Phase 8 — Auth0 / Cloudflare Access integration ---
    # ``none`` (default) keeps the legacy unauthenticated posture.
    # ``auth0`` validates Bearer JWTs against APP_AUTH_OIDC_ISSUER /
    # APP_AUTH_OIDC_AUDIENCE. ``cloudflare_access`` trusts the
    # ``Cf-Access-Authenticated-User-Email`` header injected by the
    # Cloudflare Tunnel ingress when an Access policy is in place.
    auth_provider: str = Field(default="none")
    auth_oidc_issuer: str = Field(default="")
    auth_oidc_audience: str = Field(default="")
    auth_oidc_jwks_ttl_seconds: int = Field(default=3600)
    auth_oidc_leeway_seconds: int = Field(default=60)

    # Cluster information
    cluster_name: str = Field(default="rpi-k8s-cluster", description="Cluster name")

    # Nested settings
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    mlflow: MLFlowSettings = Field(default_factory=MLFlowSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    flink: FlinkSettings = Field(default_factory=FlinkSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    docstore: DocumentStoreSettings = Field(default_factory=DocumentStoreSettings)
    alphavantage: AlphaVantageSettings = Field(default_factory=AlphaVantageSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
