"""Shared configuration helpers for pipeline runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_float(name: str, default: str) -> float:
    try:
        return float(_env(name, default))
    except ValueError:
        return float(default)


def _env_int(name: str, default: str) -> int:
    try:
        return int(_env(name, default))
    except ValueError:
        return int(default)


def _env_bool(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes", "on"}


def normalize_endpoint(endpoint: str) -> str:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    return f"http://{endpoint}"


@dataclass(slots=True)
class PipelineConfig:
    """Environment-backed configuration used by Argo and Dagster tasks."""

    minio_endpoint: str = field(
        default_factory=lambda: normalize_endpoint(
            _env("PIPELINE_MINIO_ENDPOINT", "minio.data-services.svc.cluster.local:9000")
        )
    )
    minio_access_key: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_ACCESS_KEY", "minioadmin")
    )
    minio_secret_key: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_SECRET_KEY", "minioadmin123")
    )
    minio_region: str = field(default_factory=lambda: _env("PIPELINE_MINIO_REGION", "us-east-1"))
    minio_bucket_raw: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_BUCKET_RAW", "dagster-artifacts")
    )
    minio_bucket_processed: str = field(
        default_factory=lambda: _env("PIPELINE_MINIO_BUCKET_PROCESSED", "dagster-artifacts")
    )
    postgres_dsn: str = field(
        default_factory=lambda: _env(
            "PIPELINE_POSTGRES_DSN",
            "postgresql://dagster:dagster123@postgresql.data-services.svc.cluster.local:5432/dagster",
        )
    )
    source_postgres_dsn: str = field(default_factory=lambda: _env("PIPELINE_SOURCE_POSTGRES_DSN", ""))
    milvus_host: str = field(default_factory=lambda: _env("PIPELINE_MILVUS_HOST", "milvus.data-services"))
    milvus_port: int = field(default_factory=lambda: int(_env("PIPELINE_MILVUS_PORT", "19530")))
    chroma_host: str = field(default_factory=lambda: _env("PIPELINE_CHROMA_HOST", "chromadb.data-services"))
    chroma_port: int = field(default_factory=lambda: int(_env("PIPELINE_CHROMA_PORT", "8000")))
    rest_api_token: str = field(default_factory=lambda: _env("PIPELINE_REST_API_TOKEN", ""))
    http_auth_header: str = field(default_factory=lambda: _env("PIPELINE_HTTP_AUTH_HEADER", ""))
    source_s3_endpoint: str = field(
        default_factory=lambda: normalize_endpoint(
            _env("PIPELINE_S3_ENDPOINT", "minio.data-services.svc.cluster.local:9000")
        )
    )
    source_s3_access_key: str = field(
        default_factory=lambda: _env("PIPELINE_S3_ACCESS_KEY", "minioadmin")
    )
    source_s3_secret_key: str = field(
        default_factory=lambda: _env("PIPELINE_S3_SECRET_KEY", "minioadmin123")
    )
    source_s3_region: str = field(default_factory=lambda: _env("PIPELINE_S3_REGION", "us-east-1"))
    datahub_enabled: bool = field(default_factory=lambda: _env_bool("PIPELINE_DATAHUB_ENABLED", "false"))
    datahub_gms_url: str = field(
        default_factory=lambda: normalize_endpoint(
            _env("PIPELINE_DATAHUB_GMS_URL", "datahub-datahub-gms.data-services.svc.cluster.local:8080")
        )
    )
    datahub_token: str = field(default_factory=lambda: _env("PIPELINE_DATAHUB_TOKEN", ""))
    datahub_env: str = field(default_factory=lambda: _env("PIPELINE_DATAHUB_ENV", "PROD"))
    iceberg_catalog_uri: str = field(
        default_factory=lambda: normalize_endpoint(
            _env(
                "PIPELINE_ICEBERG_CATALOG_URI",
                "datahub-datahub-gms.data-services.svc.cluster.local:8080/iceberg",
            )
        )
    )
    iceberg_warehouse: str = field(
        default_factory=lambda: _env("PIPELINE_ICEBERG_WAREHOUSE", "s3://iceberg-warehouse/")
    )
    model_bucket: str = field(default_factory=lambda: _env("PIPELINE_MODEL_BUCKET", "model-registry"))

    @property
    def effective_source_postgres_dsn(self) -> str:
        return self.source_postgres_dsn or self.postgres_dsn


@dataclass(slots=True)
class RedisSettings:
    """Shared Redis 8 Stack configuration.

    Controls the connection used by every redis_* helper module as well as
    the Redis OM models.  The primary environment contract is:

        REDIS_URL             -- full redis[s]://[:pass@]host:port/db URI
        REDIS_HOST/PORT/DB    -- used when REDIS_URL is unset
        REDIS_PASSWORD        -- shared secret (matches base-services/redis)
        REDIS_INDEX_PREFIX    -- prefix for FT.CREATE / keyspace isolation
        REDIS_CACHE_TTL_SECONDS
        REDIS_SEMANTIC_CACHE_THRESHOLD
        REDIS_TLS_ENABLED
    """

    url: str = field(
        default_factory=lambda: _env(
            "REDIS_URL",
            "redis://:ragflow123@redis.data-services.svc.cluster.local:6379/0",
        )
    )
    host: str = field(
        default_factory=lambda: _env("REDIS_HOST", "redis.data-services.svc.cluster.local")
    )
    port: int = field(default_factory=lambda: _env_int("REDIS_PORT", "6379"))
    db: int = field(default_factory=lambda: _env_int("REDIS_DB", "0"))
    password: str = field(default_factory=lambda: _env("REDIS_PASSWORD", "ragflow123"))
    index_prefix: str = field(default_factory=lambda: _env("REDIS_INDEX_PREFIX", "rpi"))
    cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("REDIS_CACHE_TTL_SECONDS", "300")
    )
    semantic_cache_threshold: float = field(
        default_factory=lambda: _env_float("REDIS_SEMANTIC_CACHE_THRESHOLD", "0.15")
    )
    tls_enabled: bool = field(default_factory=lambda: _env_bool("REDIS_TLS_ENABLED", "false"))
    socket_timeout: float = field(
        default_factory=lambda: _env_float("REDIS_SOCKET_TIMEOUT", "5.0")
    )
    socket_connect_timeout: float = field(
        default_factory=lambda: _env_float("REDIS_SOCKET_CONNECT_TIMEOUT", "3.0")
    )
    max_connections: int = field(
        default_factory=lambda: _env_int("REDIS_MAX_CONNECTIONS", "16")
    )

    def dsn(self) -> str:
        """Return a connection URL regardless of which env var was set."""
        if self.url:
            return self.url
        scheme = "rediss" if self.tls_enabled else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


def get_redis_settings() -> RedisSettings:
    return RedisSettings()

