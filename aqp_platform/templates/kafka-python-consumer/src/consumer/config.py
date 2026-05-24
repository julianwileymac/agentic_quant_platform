"""Consumer configuration."""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConsumerSettings(BaseSettings):
    """All values can be overridden via KAFKA_CONSUMER_* env vars."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_CONSUMER_", extra="ignore")

    bootstrap_servers: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094"
    )
    security_protocol: str = Field(default="SASL_SSL")
    sasl_mechanism: str = Field(default="SCRAM-SHA-512")
    sasl_username: str = Field(default="consumer-management")
    sasl_password: Optional[str] = Field(default=None)
    ssl_cafile: Optional[str] = Field(default="/etc/kafka/ca/ca.crt")

    group_id: str = Field(default="management-sample-consumer")
    topics: list[str] = Field(default_factory=lambda: ["market.bar.v1"])
    auto_offset_reset: str = Field(default="latest")
    enable_auto_commit: bool = Field(default=False)
    max_poll_records: int = Field(default=500)

    schema_registry_url: str = Field(
        default="http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"
    )
    schema_group: str = Field(default="default")

    otel_endpoint: str = Field(
        default="http://otel-collector.observability.svc.cluster.local:4317"
    )
    service_name: str = Field(default="kafka-python-consumer")
    metrics_port: int = Field(default=9301)
