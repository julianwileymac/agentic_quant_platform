"""Helpers that bridge Airbyte sync metadata into AQP engine manifests."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aqp.config import settings
from aqp.data.airbyte.models import AirbyteConnectionSpec


def build_airbyte_staging_manifest(
    connection: AirbyteConnectionSpec,
    *,
    stream: str,
    staging_uri: str | None = None,
    table: str | None = None,
    format: str = "parquet",
) -> dict[str, Any]:
    """Build a post-sync manifest that materializes staged Airbyte output.

    Airbyte remains the extraction/orchestration layer. AQP's engine reads
    the staged files or tables and writes to Iceberg through ``sink.iceberg``.
    """
    uri = staging_uri or connection.destination.staging_uri or settings.airbyte_staging_root
    source = _source_node_for_uri(uri, stream=stream, format=format)
    table_name = table or _safe_name(stream)
    namespace = connection.namespace or settings.airbyte_default_namespace
    return {
        "name": f"airbyte_{_safe_name(connection.name)}_{table_name}",
        "namespace": namespace,
        "description": f"Materialize Airbyte stream {stream} for {connection.name}",
        "source": source,
        "transforms": [],
        "sink": {
            "name": "sink.iceberg",
            "kwargs": {
                "namespace": namespace,
                "table": table_name,
                "provider": "airbyte",
                "domain": f"airbyte.{connection.source.connector_id}.{stream}",
                "source_uri": uri,
                "tags": ["airbyte", connection.source.connector_id, stream],
                "meta": {
                    "airbyte_connection_id": connection.airbyte_connection_id,
                    "source_connector_id": connection.source.connector_id,
                    "destination_connector_id": connection.destination.connector_id,
                },
            },
        },
        "compute": {"backend": connection.compute_backend or "auto"},
        "tags": ["airbyte", connection.source.connector_id],
    }


def _source_node_for_uri(uri: str, *, stream: str, format: str) -> dict[str, Any]:
    parsed = urlparse(uri)
    if parsed.scheme in {"s3", "s3a"}:
        key = parsed.path.strip("/")
        if key and not key.endswith((".parquet", ".csv", ".jsonl", ".json")):
            key = f"{key.rstrip('/')}/{stream}.{format}"
        return {
            "name": "source.s3",
            "kwargs": {
                "bucket": parsed.netloc,
                "key": key,
                "format": format,
            },
        }
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "name": "source.database",
            "kwargs": {
                "url": uri,
                "table": stream,
            },
        }
    path = Path(uri)
    if path.is_dir() or not path.suffix:
        path = path / f"{stream}.{format}"
    return {
        "name": "source.local_file",
        "kwargs": {
            "path": str(path),
            "format": format,
        },
    }


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_") or "stream"


__all__ = ["build_airbyte_staging_manifest"]
