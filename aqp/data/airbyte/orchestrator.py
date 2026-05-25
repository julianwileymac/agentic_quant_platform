"""Airbyte orchestration bridge for Fetcher subclasses."""
from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aqp.observability.fabric_bus import get_observability_bus, record_span
from aqp.services.airbyte_client import AirbyteClient, extract_job_id, normalize_job_status

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from aqp.data.fetchers.base import Fetcher

_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class AirbyteOrchestrator:
    """Bridge between fetchers and Airbyte connection management."""

    def __init__(self, client: AirbyteClient | None = None) -> None:
        if client is not None:
            self._client = client
        elif hasattr(AirbyteClient, "from_settings"):
            self._client = AirbyteClient.from_settings()
        else:
            self._client = AirbyteClient()

    def build_stream_config(self, fetcher: "Fetcher") -> dict[str, Any]:
        """Generate stream config from ``fetcher.CANONICAL_SCHEMA_CLASS``.

        Matches the Airbyte stream-definition shape documented in
        `aqp_docs/docs/concepts/data/airbyte-builder.md` and the data-fabric refactor plan:
          - stream.name = "<provider_slug>_<CanonicalSchemaClassName>"
          - stream.json_schema.{type, properties}
          - stream.supported_sync_modes = ["full_refresh", "incremental"]
          - stream.default_cursor_field = first timestamp-like field if any
          - sync_mode = "incremental" if a cursor field exists, else "full_refresh"
        """
        schema = fetcher.CANONICAL_SCHEMA_CLASS.CANONICAL_SCHEMA
        properties = {field.name: _arrow_field_to_json_schema(field) for field in schema}
        cursor_field = _first_timestamp_field(schema)
        provider_slug = str(getattr(fetcher, "PROVIDER_NAME", fetcher.__class__.__name__)).lower()
        schema_name = fetcher.CANONICAL_SCHEMA_CLASS.__name__
        stream_name = f"{provider_slug}_{schema_name}"
        sync_mode = "incremental" if cursor_field else "full_refresh"
        return {
            "stream": {
                "name": stream_name,
                "json_schema": {
                    "type": "object",
                    "properties": properties,
                },
                "supported_sync_modes": ["full_refresh", "incremental"],
                "default_cursor_field": cursor_field,
            },
            "sync_mode": sync_mode,
        }

    def trigger_sync(
        self,
        connection_id: str,
        *,
        cursor_override: datetime | None = None,
    ) -> str:
        """POST ``/v1/connections/sync`` and return Airbyte job id."""
        with record_span(
            "airbyte.trigger_sync",
            attributes={
                "connection_id": connection_id,
                "cursor_override": cursor_override.isoformat() if cursor_override else None,
            },
        ):
            payload = self._client.trigger_sync(connection_id)
        job_id = extract_job_id(payload)
        if job_id is None:
            raise RuntimeError(f"airbyte sync response missing job id for {connection_id!r}")
        return str(job_id)

    def poll_sync_status(
        self,
        job_id: str,
        *,
        timeout_s: int = 300,
        poll_interval_s: float = 5.0,
    ) -> str:
        """Poll ``/v1/jobs/{job_id}`` until terminal and return status."""
        bus = get_observability_bus()
        started = time.monotonic()
        deadline = started + max(1, int(timeout_s))

        with record_span(
            "airbyte.poll_sync_status",
            attributes={"job_id": job_id, "timeout_s": timeout_s},
        ):
            while True:
                payload = self._client.get_job(job_id)
                status = normalize_job_status(payload).value
                if status in _TERMINAL_STATUSES:
                    elapsed_ms = (time.monotonic() - started) * 1000.0
                    bus.batch_duration.record(
                        elapsed_ms,
                        attributes={"provider": "airbyte", "status": status},
                    )
                    return status
                if time.monotonic() >= deadline:
                    elapsed_ms = (time.monotonic() - started) * 1000.0
                    bus.batch_duration.record(
                        elapsed_ms,
                        attributes={"provider": "airbyte", "status": "timeout"},
                    )
                    raise TimeoutError(f"Airbyte job {job_id} did not finish in {timeout_s}s")
                time.sleep(max(0.1, float(poll_interval_s)))


def _arrow_field_to_json_schema(field: "pa.Field") -> dict[str, Any]:
    import pyarrow as pa

    dtype = field.type
    if pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
        schema: dict[str, Any] = {"type": "string"}
    elif pa.types.is_integer(dtype):
        schema = {"type": "integer"}
    elif pa.types.is_floating(dtype) or pa.types.is_decimal(dtype):
        schema = {"type": "number"}
    elif pa.types.is_timestamp(dtype):
        schema = {"type": "string", "format": "date-time"}
    elif pa.types.is_boolean(dtype):
        schema = {"type": "boolean"}
    else:
        schema = {"type": "string"}
    if field.nullable:
        schema["nullable"] = True
    return schema


def _first_timestamp_field(schema: "pa.Schema") -> str | None:
    import pyarrow as pa

    for field in schema:
        if pa.types.is_timestamp(field.type):
            return field.name
    return None


__all__ = ["AirbyteOrchestrator"]
