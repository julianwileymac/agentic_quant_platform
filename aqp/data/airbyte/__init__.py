"""Airbyte integration surface for AQP's data fabric."""
from __future__ import annotations

from aqp.data.airbyte.embedded import EmbeddedAirbyteRunner
from aqp.data.airbyte.models import (
    AirbyteConnectionSpec,
    AirbyteConnectorDefinition,
    AirbyteDestinationConfig,
    AirbyteDiscoverRequest,
    AirbyteEmbeddedReadRequest,
    AirbyteSourceConfig,
    AirbyteStreamSpec,
    AirbyteSyncRequest,
    AirbyteSyncResult,
    ConnectorKind,
    ConnectorRuntime,
    DestinationSyncMode,
    SyncMode,
    SyncStatus,
)
from aqp.data.airbyte.registry import (
    connector_summary,
    get_connector,
    list_connectors,
    stream_entity_mappings,
)

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
    "EmbeddedAirbyteRunner",
    "SyncMode",
    "SyncStatus",
    "connector_summary",
    "get_connector",
    "list_connectors",
    "stream_entity_mappings",
]
