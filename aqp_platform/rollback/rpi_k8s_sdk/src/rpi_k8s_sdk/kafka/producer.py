"""Synchronous Avro producer backed by confluent-kafka + Apicurio."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .registry import ApicurioClient

logger = logging.getLogger(__name__)


class AvroProducer:
    """Context-managed Avro producer.

    Usage:

        with AvroProducer(
            bootstrap="...",
            username="producer-market",
            password=...,
            schema_registry_url="...",
        ) as p:
            p.produce(topic="market.trade.v1", schema="market_trade_v1", record=..., key="AAPL")
            p.flush()
    """

    def __init__(
        self,
        *,
        bootstrap: str,
        schema_registry_url: str = "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2",
        schema_group: str = "default",
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_protocol: str = "SASL_SSL",
        sasl_mechanism: str = "SCRAM-SHA-512",
        ssl_cafile: Optional[str] = None,
        client_id: str = "rpi-k8s-sdk-producer",
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:
            raise ImportError(
                "confluent-kafka is required; install with `pip install rpi_k8s_sdk[streaming]`"
            ) from exc

        cfg: Dict[str, Any] = {
            "bootstrap.servers": bootstrap,
            "client.id": client_id,
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "snappy",
            "linger.ms": 10,
        }
        if username:
            cfg.update(
                {
                    "security.protocol": security_protocol,
                    "sasl.mechanism": sasl_mechanism,
                    "sasl.username": username,
                    "sasl.password": password or "",
                }
            )
        if ssl_cafile:
            cfg["ssl.ca.location"] = ssl_cafile
        if extra_config:
            cfg.update(extra_config)

        self._producer = Producer(cfg)
        self._registry = ApicurioClient(schema_registry_url, schema_group)

    # ------------------------------------------------------------------

    def __enter__(self) -> "AvroProducer":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def registry(self) -> ApicurioClient:
        return self._registry

    # ------------------------------------------------------------------
    # Core produce
    # ------------------------------------------------------------------

    def produce(
        self,
        *,
        topic: str,
        schema: str,
        record: Dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[Dict[str, bytes]] = None,
    ) -> None:
        payload = self._registry.encode(schema, record)
        self._producer.produce(
            topic=topic,
            key=key.encode() if key else None,
            value=payload,
            headers=list(headers.items()) if headers else None,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)

    def close(self) -> None:
        self._producer.flush(15.0)
        self._registry.close()
