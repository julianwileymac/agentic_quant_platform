"""Avro schemas for the AQP streaming pipeline.

The schemas here are the single source of truth shared by:

- ``aqp.streaming.ingesters`` (producers): serialize IBKR/Alpaca events to Kafka
- The Flink PyFlink jobs at ``rpi_kubernetes/flink-jobs/`` (produce + consume)
- ``aqp.trading.feeds.kafka_feed.KafkaDataFeed`` (consumer): materializes
  records back into :mod:`aqp.core.types` (``BarData``, ``TickData``, ``Signal``)

Each schema lives in a sibling ``*.avsc`` file; this module exposes helpers
that read + parse + cache them and emit ready-to-use ``fastavro`` serializers.
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMAS_DIR",
    "SCHEMA_NAMES",
    "TOPIC_BY_SCHEMA",
    "SCHEMA_BY_TOPIC",
    "load_schema",
    "list_schemas",
    "avro_encode",
    "avro_decode",
    "topic_for",
    "schema_for_topic",
]

SCHEMAS_DIR = Path(__file__).resolve().parent

# Canonical mapping of schema file stem -> Kafka topic. The schema stem is
# also the shortname used by the rest of the platform (config, Flink jobs,
# CLI arguments). Keep this table in lock-step with the topic list in
# ``rpi_kubernetes/kubernetes/base-services/kafka/topics.yaml``.
TOPIC_BY_SCHEMA: dict[str, str] = {
    "market_trade_v1": "market.trade.v1",
    "market_quote_v1": "market.quote.v1",
    "market_bar_v1": "market.bar.v1",
    "market_snapshot_v1": "market.snapshot.v1",
    "market_scanner_v1": "market.scanner.v1",
    "market_contract_v1": "market.contract.v1",
    "market_imbalance_v1": "market.imbalance.v1",
    "market_status_v1": "market.status.v1",
    "market_correction_v1": "market.correction.v1",
    "features_indicators_v1": "features.indicators.v1",
    "features_normalized_v1": "features.normalized.v1",
    "features_signals_v1": "features.signals.v1",
}

SCHEMA_BY_TOPIC: dict[str, str] = {v: k for k, v in TOPIC_BY_SCHEMA.items()}
SCHEMA_NAMES: tuple[str, ...] = tuple(TOPIC_BY_SCHEMA.keys())


def list_schemas() -> list[str]:
    """Return the canonical ordered list of schema shortnames."""
    return list(SCHEMA_NAMES)


def topic_for(schema_name: str) -> str:
    try:
        return TOPIC_BY_SCHEMA[schema_name]
    except KeyError as exc:
        raise KeyError(f"Unknown schema shortname: {schema_name!r}") from exc


def schema_for_topic(topic: str) -> str:
    try:
        return SCHEMA_BY_TOPIC[topic]
    except KeyError as exc:
        raise KeyError(f"Unknown topic: {topic!r}") from exc


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    """Load and cache the parsed Avro schema for ``schema_name``."""
    path = SCHEMAS_DIR / f"{schema_name}.avsc"
    if not path.exists():
        raise FileNotFoundError(f"Avro schema not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _parsed_schema(schema_name: str) -> Any:
    """Return a ``fastavro``-parsed schema object (lazy import)."""
    try:
        from fastavro import parse_schema  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError(
            'Streaming requires the "streaming" extra. '
            'Install with: pip install -e ".[streaming]"'
        ) from exc
    return parse_schema(load_schema(schema_name))


def avro_encode(schema_name: str, record: dict[str, Any]) -> bytes:
    """Encode ``record`` as an Avro single-object (schemaless) payload.

    We intentionally do not use Confluent's schema-registry wire format
    (magic byte + schema id) because we want the schemas bundled with the
    code in both the ingester and the Flink jobs. The Flink side reads the
    same ``*.avsc`` files via PyAvro.
    """
    try:
        from fastavro import schemaless_writer  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            'Streaming requires the "streaming" extra. '
            'Install with: pip install -e ".[streaming]"'
        ) from exc
    buf = io.BytesIO()
    schemaless_writer(buf, _parsed_schema(schema_name), record)
    return buf.getvalue()


def avro_decode(schema_name: str, payload: bytes) -> dict[str, Any]:
    """Decode an Avro single-object payload using the named schema."""
    try:
        from fastavro import schemaless_reader  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            'Streaming requires the "streaming" extra. '
            'Install with: pip install -e ".[streaming]"'
        ) from exc
    buf = io.BytesIO(payload)
    return schemaless_reader(buf, _parsed_schema(schema_name))  # type: ignore[return-value]
