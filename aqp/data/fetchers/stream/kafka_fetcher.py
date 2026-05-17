"""Kafka micro-batch consumer fetcher.

Polls a Kafka topic for ``max_messages`` (or until ``timeout_seconds``
elapses) and yields the consumed messages as Arrow batches. Best for
backfill / preview scenarios; for true streaming, plug into Flink /
Spark Structured Streaming downstream.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.kafka",
    display_name="Kafka Topic (micro-batch)",
    kind=FetcherKind.STREAM,
    description="Consume a Kafka topic for a fixed batch and yield Arrow rows.",
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.SUPPORTS_PARALLELISM.value,
    ),
    domains=("stream.kafka",),
    auth_type="optional_sasl",
)
class KafkaFetcher(Fetcher):
    """Consume ``topic`` for a bounded micro-batch window.

    Each Kafka message is parsed as JSON; the parsed dict (plus
    ``__topic``, ``__partition``, ``__offset``, ``__key``) becomes one
    row. ``max_messages`` and ``timeout_seconds`` bound the read so the
    fetcher always returns even on an idle topic.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        topic: str,
        bootstrap_servers: str | None = None,
        group_id: str | None = None,
        max_messages: int = 1_000,
        timeout_seconds: float = 5.0,
        auto_offset_reset: str = "earliest",
        chunk_rows: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.max_messages = max(1, int(max_messages))
        self.timeout_seconds = float(timeout_seconds)
        self.auto_offset_reset = str(auto_offset_reset)
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        bs = self.bootstrap_servers or "kafka"
        return f"kafka://{bs}/{self.topic}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.config import settings

        try:
            from confluent_kafka import Consumer
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise RuntimeError(f"KafkaFetcher requires confluent-kafka: {exc}") from exc

        bootstrap = self.bootstrap_servers or settings.kafka_bootstrap
        consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": self.group_id or settings.kafka_consumer_group or "aqp-fetcher",
                "auto.offset.reset": self.auto_offset_reset,
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe([self.topic])

        rows: list[dict[str, Any]] = []
        consumed = 0
        try:
            while consumed < self.max_messages:
                msg = consumer.poll(timeout=self.timeout_seconds)
                if msg is None:
                    break
                if msg.error():
                    logger.warning("kafka error: %s", msg.error())
                    continue
                try:
                    body = json.loads(msg.value().decode("utf-8")) if msg.value() else {}
                    if not isinstance(body, dict):
                        body = {"__value": body}
                except Exception:  # noqa: BLE001
                    body = {"__value": msg.value().decode("utf-8", errors="replace")}
                body.update(
                    {
                        "__topic": msg.topic(),
                        "__partition": msg.partition(),
                        "__offset": msg.offset(),
                        "__key": (msg.key().decode("utf-8", errors="replace") if msg.key() else None),
                    }
                )
                rows.append(body)
                consumed += 1
                if len(rows) >= self.chunk_rows:
                    yield from self._to_batches(rows)
                    rows = []
            if rows:
                yield from self._to_batches(rows)
            consumer.commit(asynchronous=False)
        finally:
            consumer.close()

    @staticmethod
    def _to_batches(rows: list[dict[str, Any]]) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        yield from table.to_batches()
