"""Producer configuration driven by environment variables."""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProducerSettings(BaseSettings):
    """All values can be overridden via KAFKA_PRODUCER_* env vars."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_PRODUCER_", extra="ignore")

    # Kafka connection
    bootstrap_servers: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094",
        description="Kafka bootstrap servers for the SCRAM (9094) listener.",
    )
    security_protocol: str = Field(default="SASL_SSL")
    sasl_mechanism: str = Field(default="SCRAM-SHA-512")
    sasl_username: str = Field(default="producer-market")
    sasl_password: Optional[str] = Field(
        default=None,
        description="Usually mounted from the KafkaUser secret `producer-market/password`.",
    )
    ssl_ca_location: Optional[str] = Field(
        default="/etc/kafka/ca/ca.crt",
        description="Path to the Strimzi cluster CA certificate inside the pod.",
    )

    # Target
    topic: str = Field(default="market.trade.v1")
    deadletter_topic: str = Field(default="market.deadletter.v1")

    # Avro / Schema Registry
    schema_registry_url: str = Field(
        default="http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"
    )
    schema_group: str = Field(default="default")
    schema_name: str = Field(default="market_trade_v1")

    # Tracing
    otel_endpoint: str = Field(
        default="http://otel-collector.observability.svc.cluster.local:4317"
    )
    service_name: str = Field(default="kafka-python-producer")

    # Runtime
    metrics_port: int = Field(default=9300)
    rate_per_second: int = Field(default=10)
