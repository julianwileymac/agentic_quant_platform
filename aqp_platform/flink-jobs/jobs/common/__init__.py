"""Shared helpers for AQP PyFlink jobs."""
from __future__ import annotations

from jobs.common.schemas import (
    SCHEMA_NAMES,
    TOPIC_BY_SCHEMA,
    avro_decode,
    avro_encode,
    load_schema,
    topic_for,
)
from jobs.common.kafka import build_consumer, build_producer
from jobs.common.sinks import (
    build_jdbc_sink,
    build_parquet_sink,
    build_victoriametrics_sink,
)

__all__ = [
    "SCHEMA_NAMES",
    "TOPIC_BY_SCHEMA",
    "avro_decode",
    "avro_encode",
    "build_consumer",
    "build_jdbc_sink",
    "build_parquet_sink",
    "build_producer",
    "build_victoriametrics_sink",
    "load_schema",
    "topic_for",
]
