"""Typed Airbyte contracts used by AQP's data fabric control plane."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectorKind(str, Enum):
    SOURCE = "source"
    DESTINATION = "destination"


class ConnectorRuntime(str, Enum):
    FULL_AIRBYTE = "full_airbyte"
    EMBEDDED = "embedded"
    HYBRID = "hybrid"


class SyncMode(str, Enum):
    FULL_REFRESH = "full_refresh"
    INCREMENTAL = "incremental"


class DestinationSyncMode(str, Enum):
    APPEND = "append"
    APPEND_DEDUP = "append_dedup"
    OVERWRITE = "overwrite"


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class AirbyteStreamSpec(BaseModel):
    """Stream metadata from a connector catalog or AQP registry entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    namespace: str | None = None
    json_schema: dict[str, Any] = Field(default_factory=dict)
    supported_sync_modes: list[SyncMode] = Field(default_factory=lambda: [SyncMode.FULL_REFRESH])
    default_sync_mode: SyncMode = SyncMode.FULL_REFRESH
    destination_sync_mode: DestinationSyncMode = DestinationSyncMode.APPEND
    cursor_field: list[str] = Field(default_factory=list)
    primary_key: list[list[str]] = Field(default_factory=list)
    selected: bool = True
    entity_kind: str | None = None
    entity_identifier_fields: list[str] = Field(default_factory=list)


class AirbyteConnectorDefinition(BaseModel):
    """AQP-curated connector definition for full Airbyte and embedded flows."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: ConnectorKind
    runtime: ConnectorRuntime = ConnectorRuntime.HYBRID
    description: str = ""
    service: str | None = None
    airbyte_definition_id: str | None = None
    docker_repository: str | None = None
    docker_image_tag: str | None = None
    python_package: str | None = None
    source_manifest_path: str | None = None
    docs_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    streams: list[AirbyteStreamSpec] = Field(default_factory=list)
    default_destination: str | None = None
    staging: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _slug(cls, value: str) -> str:
        slug = value.strip().lower().replace(" ", "-")
        if not slug:
            raise ValueError("connector id must not be empty")
        return slug


class AirbyteDestinationConfig(BaseModel):
    """Destination selected for a sync run."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    airbyte_destination_id: str | None = None
    staging_uri: str | None = None


class AirbyteSourceConfig(BaseModel):
    """Source connector config owned by AQP."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    airbyte_source_id: str | None = None


class AirbyteConnectionSpec(BaseModel):
    """A configured source -> destination Airbyte connection."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    source: AirbyteSourceConfig
    destination: AirbyteDestinationConfig
    streams: list[AirbyteStreamSpec] = Field(default_factory=list)
    namespace: str = "aqp_airbyte"
    schedule: dict[str, Any] = Field(default_factory=dict)
    catalog: dict[str, Any] = Field(default_factory=dict)
    entity_mappings: list[dict[str, Any]] = Field(default_factory=list)
    materialization_manifest: dict[str, Any] | None = None
    compute_backend: Literal["auto", "local", "dask", "ray"] = "auto"
    airbyte_connection_id: str | None = None
    enabled: bool = True


class AirbyteDiscoverRequest(BaseModel):
    connector_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    runtime: ConnectorRuntime = ConnectorRuntime.EMBEDDED


class AirbyteEmbeddedReadRequest(BaseModel):
    connector_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    streams: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=10_000)
    cache_name: str | None = None
    dry_run: bool = True


class AirbyteSyncRequest(BaseModel):
    connection_id: str | None = None
    spec: AirbyteConnectionSpec | None = None
    wait: bool = False
    poll_interval_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    timeout_seconds: int | None = Field(default=None, ge=1)
    materialize_after_sync: bool = False


class AirbyteSyncResult(BaseModel):
    run_id: str | None = None
    connection_id: str | None = None
    airbyte_connection_id: str | None = None
    airbyte_job_id: str | None = None
    status: SyncStatus = SyncStatus.UNKNOWN
    started_at: datetime | None = None
    finished_at: datetime | None = None
    records_synced: int = 0
    bytes_synced: int = 0
    streams: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


__all__ = [
    "AirbyteConnectionSpec",
    "AirbyteConnectorDefinition",
    "AirbyteDestinationConfig",
    "AirbyteDiscoverRequest",
    "AirbyteEmbeddedReadRequest",
    "AirbyteSourceConfig",
    "AirbyteStreamSpec",
    "AirbyteSyncRequest",
    "AirbyteSyncResult",
    "ConnectorKind",
    "ConnectorRuntime",
    "DestinationSyncMode",
    "SyncMode",
    "SyncStatus",
]
