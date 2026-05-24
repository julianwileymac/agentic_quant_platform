"""Async Avro consumer backed by aiokafka + Apicurio."""

from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from .registry import ApicurioClient

logger = logging.getLogger(__name__)


@dataclass
class AvroMessage:
    topic: str
    partition: int
    offset: int
    key: Optional[str]
    value: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp_ns: Optional[int] = None


class AvroConsumer:
    """Async context-managed Avro consumer.

    Usage:

        async with AvroConsumer(
            bootstrap="...",
            topics=["market.bar.v1"],
            group_id="my-strategy",
            username="consumer-management",
            password=...,
        ) as consumer:
            async for msg in consumer:
                print(msg.topic, msg.value)
    """

    def __init__(
        self,
        *,
        bootstrap: str,
        topics: List[str],
        group_id: str,
        schema_registry_url: str = "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2",
        schema_group: str = "default",
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_protocol: str = "SASL_SSL",
        sasl_mechanism: str = "SCRAM-SHA-512",
        ssl_cafile: Optional[str] = None,
        auto_offset_reset: str = "latest",
        enable_auto_commit: bool = False,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError as exc:
            raise ImportError(
                "aiokafka is required; install with `pip install rpi_k8s_sdk[streaming]`"
            ) from exc

        ctx: Optional[ssl.SSLContext] = None
        if ssl_cafile and security_protocol.startswith("SASL_SSL"):
            ctx = ssl.create_default_context(cafile=ssl_cafile)

        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=enable_auto_commit,
            security_protocol=security_protocol if username else "PLAINTEXT",
            sasl_mechanism=sasl_mechanism if username else None,
            sasl_plain_username=username,
            sasl_plain_password=password,
            ssl_context=ctx,
            **(extra_config or {}),
        )
        self._topics = topics
        self._registry = ApicurioClient(schema_registry_url, schema_group)
        self._enable_auto_commit = enable_auto_commit

    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AvroConsumer":
        await self._consumer.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        try:
            await self._consumer.stop()
        finally:
            self._registry.close()

    def __aiter__(self) -> AsyncIterator[AvroMessage]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[AvroMessage]:
        async for msg in self._consumer:
            try:
                value = self._registry.decode(msg.value)
            except Exception:  # noqa: BLE001
                logger.exception("decode failed for %s", msg.topic)
                continue
            key = msg.key.decode() if isinstance(msg.key, (bytes, bytearray)) else msg.key
            headers = {
                k: (v.decode() if isinstance(v, (bytes, bytearray)) else v)
                for k, v in (msg.headers or [])
            }
            yield AvroMessage(
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
                key=key,
                value=value,
                headers=headers,
                timestamp_ns=msg.timestamp * 1_000_000 if msg.timestamp else None,
            )
            if not self._enable_auto_commit:
                await self._consumer.commit()
