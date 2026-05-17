"""Kafka sink — publishes batches as JSON to a topic.

Optional dependency: ``confluent-kafka`` (already in the streaming
extra). Best-effort: missing dep logs and skips.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "sink.kafka",
    description="Publish Arrow rows to a Kafka topic as JSON.",
    tags=("kafka", "stream"),
)
class KafkaSink(SinkNode):
    """Publish each row of every batch as a JSON message to ``topic``.

    ``key_column`` selects the column whose value becomes the Kafka
    message key (optional).
    """

    def __init__(
        self,
        *,
        topic: str,
        bootstrap_servers: str | None = None,
        key_column: str | None = None,
        flush_every: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.topic = str(topic)
        self.bootstrap_servers = bootstrap_servers
        self.key_column = key_column
        self.flush_every = max(1, int(flush_every))

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        from aqp.config import settings

        try:
            from confluent_kafka import Producer
        except Exception as exc:  # noqa: BLE001 - optional dep missing
            logger.warning("KafkaSink unavailable (%s); skipping", exc)
            return {"rows_written": 0, "error": f"kafka_unavailable: {exc}"}

        bootstrap = self.bootstrap_servers or settings.kafka_bootstrap
        producer = Producer(
            {
                "bootstrap.servers": bootstrap,
                "client.id": settings.kafka_client_id or "aqp-sink",
                "compression.type": settings.kafka_compression or "zstd",
                "acks": settings.kafka_acks or "all",
            }
        )

        rows = 0
        for batch in batches:
            if batch.num_rows == 0:
                continue
            df = batch.to_pandas()
            for idx, row in df.iterrows():
                key = (
                    str(row[self.key_column])
                    if self.key_column and self.key_column in df.columns
                    else None
                )
                payload = json.dumps(row.to_dict(), default=str).encode("utf-8")
                producer.produce(
                    self.topic,
                    value=payload,
                    key=key.encode("utf-8") if key else None,
                )
                rows += 1
                if rows % self.flush_every == 0:
                    producer.poll(0)
        producer.flush()
        ctx.emit("sink", f"kafka published rows={rows}")
        return {
            "rows_written": rows,
            "tables": [
                {
                    "family": self.topic,
                    "iceberg_identifier": "",
                    "table_name": self.topic,
                    "rows_written": rows,
                }
            ],
        }
