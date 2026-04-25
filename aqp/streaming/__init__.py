"""AQP streaming subpackage.

Runs 24/7 market-data ingesters (IBKR + Alpaca) that publish canonical
Avro-schemed events to the Kafka cluster deployed by ``rpi_kubernetes``.

Public entrypoints:

- ``aqp.streaming.schemas`` -- Avro schemas + (de)serializers
- ``aqp.streaming.kafka_producer`` -- shared producer + metrics
- ``aqp.streaming.ingesters`` -- ``IBKRIngester``, ``AlpacaIngester``
- ``aqp.streaming.runtime`` / ``aqp.streaming.cli`` -- ``aqp-stream-ingest`` CLI
"""
from __future__ import annotations

from aqp.streaming.schemas import (
    SCHEMA_NAMES,
    TOPIC_BY_SCHEMA,
    avro_decode,
    avro_encode,
    load_schema,
    schema_for_topic,
    topic_for,
)

__all__ = [
    "SCHEMA_NAMES",
    "TOPIC_BY_SCHEMA",
    "avro_encode",
    "avro_decode",
    "load_schema",
    "schema_for_topic",
    "topic_for",
]
