"""Native Kafka admin client.

Wraps ``confluent_kafka.admin.AdminClient`` with helpers used by the
``/streaming/kafka`` API routes (list / create / delete topics, list
consumer groups + lag, sample messages). The client is lazy: instances
fail-fast when the underlying SDK is missing or the cluster is
unreachable, but importing this module never raises.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


class KafkaAdminError(RuntimeError):
    """Raised when a Kafka admin operation fails."""


class KafkaAdminUnavailableError(KafkaAdminError):
    """Raised when ``confluent_kafka`` is not installed."""


@dataclass(frozen=True)
class TopicSummary:
    name: str
    partitions: int
    replication_factor: int
    config: dict[str, str]
    is_internal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "partitions": int(self.partitions),
            "replication_factor": int(self.replication_factor),
            "config": dict(self.config),
            "is_internal": bool(self.is_internal),
        }


@dataclass(frozen=True)
class ConsumerGroupSummary:
    group_id: str
    state: str
    members: int
    topics: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "state": self.state,
            "members": int(self.members),
            "topics": list(self.topics),
        }


def _admin_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "bootstrap.servers": settings.kafka_admin_bootstrap or settings.kafka_bootstrap,
        "client.id": "aqp-admin",
    }
    protocol = getattr(settings, "kafka_admin_security_protocol", None) or settings.kafka_security_protocol
    if protocol:
        cfg["security.protocol"] = protocol
    mech = getattr(settings, "kafka_admin_sasl_mechanism", None) or settings.kafka_sasl_mechanism
    if mech:
        cfg["sasl.mechanism"] = mech
    user = getattr(settings, "kafka_admin_sasl_username", None) or settings.kafka_sasl_username
    if user:
        cfg["sasl.username"] = user
    password = getattr(settings, "kafka_admin_sasl_password", None) or settings.kafka_sasl_password
    if password:
        cfg["sasl.password"] = password
    return cfg


class NativeKafkaAdmin:
    """Thin facade over confluent_kafka.admin.AdminClient."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or _admin_config()
        self._lock = threading.Lock()
        self._client: Any | None = None

    def _get_client(self) -> Any:
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from confluent_kafka.admin import AdminClient  # type: ignore[import]
            except Exception as exc:  # pragma: no cover - optional dep
                raise KafkaAdminUnavailableError(
                    "confluent_kafka.admin not installed"
                ) from exc
            try:
                self._client = AdminClient(self._config)
            except Exception as exc:  # noqa: BLE001
                raise KafkaAdminError(f"failed to construct AdminClient: {exc}") from exc
            return self._client

    # ---------------- topics
    def list_topics(
        self,
        *,
        include_internal: bool = False,
        timeout_s: float = 10.0,
    ) -> list[TopicSummary]:
        client = self._get_client()
        try:
            metadata = client.list_topics(timeout=timeout_s)
        except Exception as exc:  # noqa: BLE001
            raise KafkaAdminError(f"list_topics failed: {exc}") from exc
        out: list[TopicSummary] = []
        for name, topic in (metadata.topics or {}).items():
            is_internal = bool(name.startswith("__"))
            if not include_internal and is_internal:
                continue
            partitions = len(getattr(topic, "partitions", {}) or {})
            replication = (
                len(next(iter(topic.partitions.values())).replicas)
                if partitions and topic.partitions
                else 0
            )
            out.append(
                TopicSummary(
                    name=name,
                    partitions=partitions,
                    replication_factor=replication,
                    config={},
                    is_internal=is_internal,
                )
            )
        out.sort(key=lambda t: t.name)
        return out

    def get_topic(self, name: str, *, timeout_s: float = 10.0) -> TopicSummary:
        for topic in self.list_topics(include_internal=True, timeout_s=timeout_s):
            if topic.name == name:
                return topic
        raise KafkaAdminError(f"topic {name!r} not found")

    def create_topic(
        self,
        name: str,
        *,
        partitions: int = 1,
        replication_factor: int = 1,
        config: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> TopicSummary:
        client = self._get_client()
        try:
            from confluent_kafka.admin import NewTopic  # type: ignore[import]
        except Exception as exc:  # pragma: no cover
            raise KafkaAdminUnavailableError("confluent_kafka.admin missing NewTopic") from exc
        new = NewTopic(
            topic=name,
            num_partitions=int(partitions),
            replication_factor=int(replication_factor),
            config=dict(config or {}),
        )
        futures = client.create_topics([new], request_timeout=timeout_s)
        for topic_name, future in (futures or {}).items():
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                raise KafkaAdminError(f"create_topic {topic_name} failed: {exc}") from exc
        return self.get_topic(name, timeout_s=timeout_s)

    def delete_topic(self, name: str, *, timeout_s: float = 30.0) -> None:
        client = self._get_client()
        futures = client.delete_topics([name], request_timeout=timeout_s)
        for topic_name, future in (futures or {}).items():
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                raise KafkaAdminError(f"delete_topic {topic_name} failed: {exc}") from exc

    # ---------------- consumer groups
    def list_consumer_groups(self, *, timeout_s: float = 10.0) -> list[ConsumerGroupSummary]:
        client = self._get_client()
        try:
            future = client.list_consumer_groups(request_timeout=timeout_s)
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            raise KafkaAdminError(f"list_consumer_groups failed: {exc}") from exc
        rows: list[ConsumerGroupSummary] = []
        for group in getattr(result, "valid", []) or []:
            rows.append(
                ConsumerGroupSummary(
                    group_id=getattr(group, "group_id", str(group)),
                    state=str(getattr(group, "state", "unknown")),
                    members=int(getattr(group, "member_count", 0) or 0),
                    topics=[],
                )
            )
        return rows

    def get_consumer_group_lag(
        self, group_id: str, *, timeout_s: float = 10.0
    ) -> dict[str, Any]:
        try:
            from confluent_kafka import (  # type: ignore[import]
                Consumer,
                TopicPartition,
            )
        except Exception as exc:  # pragma: no cover
            raise KafkaAdminUnavailableError("confluent_kafka missing Consumer") from exc
        try:
            consumer = Consumer(
                {**self._config, "group.id": group_id, "enable.auto.commit": False}
            )
        except Exception as exc:  # noqa: BLE001
            raise KafkaAdminError(f"consumer creation failed: {exc}") from exc
        try:
            metadata = consumer.list_topics(timeout=timeout_s)
            partitions: list[TopicPartition] = []
            for name, topic in (metadata.topics or {}).items():
                if name.startswith("__"):
                    continue
                for pid in (topic.partitions or {}):
                    partitions.append(TopicPartition(name, pid))
            committed = consumer.committed(partitions, timeout=timeout_s)
            out: list[dict[str, Any]] = []
            for tp in committed:
                low, high = consumer.get_watermark_offsets(tp, timeout=timeout_s)
                committed_offset = tp.offset if tp.offset >= 0 else 0
                out.append(
                    {
                        "topic": tp.topic,
                        "partition": tp.partition,
                        "low": int(low),
                        "high": int(high),
                        "committed": int(committed_offset),
                        "lag": max(0, int(high) - int(committed_offset)),
                    }
                )
            return {"group_id": group_id, "partitions": out}
        finally:
            try:
                consumer.close()
            except Exception:  # noqa: BLE001
                pass

    # ---------------- sampling
    async def sample_messages(
        self, topic: str, *, limit: int = 100, timeout_s: float = 5.0
    ) -> list[dict[str, Any]]:
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore[import]
        except Exception as exc:  # pragma: no cover
            raise KafkaAdminUnavailableError("aiokafka not installed") from exc
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self._config["bootstrap.servers"],
            group_id=None,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            consumer_timeout_ms=int(timeout_s * 1000),
        )
        await consumer.start()
        out: list[dict[str, Any]] = []
        try:
            async for msg in consumer:
                payload: Any
                try:
                    payload = msg.value.decode("utf-8") if msg.value else None
                except Exception:  # noqa: BLE001
                    payload = repr(msg.value)
                out.append(
                    {
                        "topic": msg.topic,
                        "partition": int(msg.partition),
                        "offset": int(msg.offset),
                        "timestamp": int(msg.timestamp) if msg.timestamp else None,
                        "key": msg.key.decode("utf-8") if msg.key else None,
                        "value_preview": (payload or "")[:1024]
                        if isinstance(payload, str)
                        else None,
                    }
                )
                if len(out) >= limit:
                    break
        finally:
            await consumer.stop()
        return out


_singleton: NativeKafkaAdmin | None = None
_singleton_lock = threading.Lock()


def get_kafka_admin() -> NativeKafkaAdmin:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = NativeKafkaAdmin()
        return _singleton


__all__ = [
    "ConsumerGroupSummary",
    "KafkaAdminError",
    "KafkaAdminUnavailableError",
    "NativeKafkaAdmin",
    "TopicSummary",
    "get_kafka_admin",
]
