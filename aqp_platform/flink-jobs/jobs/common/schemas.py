"""Avro schema helpers for PyFlink jobs.

Mirrors ``agentic_quant_platform/aqp/streaming/schemas/`` so producers and
Flink consumers decode/encode the same bytes. The schema files live under
``jobs/schemas/`` and are copied into the image by the Dockerfile.
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

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
SCHEMA_BY_TOPIC = {v: k for k, v in TOPIC_BY_SCHEMA.items()}
SCHEMA_NAMES = tuple(TOPIC_BY_SCHEMA.keys())


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / f"{schema_name}.avsc"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _parsed(schema_name: str) -> Any:
    from fastavro import parse_schema  # type: ignore[import]

    return parse_schema(load_schema(schema_name))


def avro_encode(schema_name: str, record: dict[str, Any]) -> bytes:
    from fastavro import schemaless_writer  # type: ignore[import]

    buf = io.BytesIO()
    schemaless_writer(buf, _parsed(schema_name), record)
    return buf.getvalue()


def avro_decode(schema_name: str, payload: bytes) -> dict[str, Any]:
    from fastavro import schemaless_reader  # type: ignore[import]

    buf = io.BytesIO(payload)
    return schemaless_reader(buf, _parsed(schema_name))  # type: ignore[return-value]


def topic_for(schema_name: str) -> str:
    return TOPIC_BY_SCHEMA[schema_name]


def schema_for(topic: str) -> str:
    return SCHEMA_BY_TOPIC[topic]


__all__ = [
    "SCHEMAS_DIR",
    "SCHEMA_BY_TOPIC",
    "SCHEMA_NAMES",
    "TOPIC_BY_SCHEMA",
    "avro_decode",
    "avro_encode",
    "load_schema",
    "schema_for",
    "topic_for",
]
