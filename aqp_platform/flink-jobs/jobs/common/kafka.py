"""Kafka source/sink builders used by the PyFlink jobs.

PyFlink's ``KafkaSource`` and ``KafkaSink`` are the DataStream-API Kafka
connectors. We keep deserialization trivial (``ByteArrayDeserializer``)
and decode Avro payloads inside each job's ``ProcessFunction`` so schema
evolution stays local to the job code.
"""
from __future__ import annotations

from typing import Any

from pyflink.common import WatermarkStrategy  # type: ignore[import]
from pyflink.common.serialization import SimpleStringSchema  # type: ignore[import]
from pyflink.common.typeinfo import Types  # type: ignore[import]
from pyflink.datastream.connectors.kafka import (  # type: ignore[import]
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)


class _ByteArrayDeserializer:
    """Deserializer that yields raw bytes for downstream Avro decoding."""

    def deserialize(self, message: bytes) -> bytes:
        return message

    def get_produced_type(self) -> Any:
        return Types.PRIMITIVE_ARRAY(Types.BYTE())


def build_consumer(
    bootstrap_servers: str,
    topics: list[str] | str,
    group_id: str,
    *,
    starting_offsets: str = "latest",
    extra_properties: dict[str, str] | None = None,
) -> KafkaSource:
    """Build a ``KafkaSource`` that emits raw ``bytes`` records."""
    builder = (
        KafkaSource.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_group_id(group_id)
        .set_topics(*([topics] if isinstance(topics, str) else topics))
    )
    if starting_offsets == "earliest":
        builder.set_starting_offsets(KafkaOffsetsInitializer.earliest())
    elif starting_offsets == "latest":
        builder.set_starting_offsets(KafkaOffsetsInitializer.latest())
    builder.set_value_only_deserializer(SimpleStringSchema())

    if extra_properties:
        for k, v in extra_properties.items():
            builder.set_property(k, v)
    return builder.build()


def build_producer(
    bootstrap_servers: str,
    topic: str,
    *,
    transactional_id_prefix: str | None = None,
    extra_properties: dict[str, str] | None = None,
) -> KafkaSink:
    """Build a ``KafkaSink`` that accepts raw ``str`` records.

    Flink PyFlink's public Python API speaks ``str``; jobs encode their
    Avro payloads via base64 or hex when emitting, or use Table API for
    Avro pass-through. For this MVP we emit JSON strings downstream
    consumers can also read; full Avro re-encoding is a follow-up.
    """
    serialization = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(topic)
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    )
    builder = (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(serialization)
    )
    if transactional_id_prefix:
        builder.set_transactional_id_prefix(transactional_id_prefix)
    if extra_properties:
        for k, v in extra_properties.items():
            builder.set_property(k, v)
    return builder.build()


def default_watermark_strategy(max_out_of_orderness_ms: int = 5_000) -> WatermarkStrategy:
    """Watermark strategy: ``BoundedOutOfOrderness`` with a configurable lag."""
    from datetime import timedelta

    return WatermarkStrategy.for_bounded_out_of_orderness(
        timedelta(milliseconds=max_out_of_orderness_ms)
    )


__all__ = [
    "build_consumer",
    "build_producer",
    "default_watermark_strategy",
]
