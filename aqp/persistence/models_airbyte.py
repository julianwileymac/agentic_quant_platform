"""Airbyte control-plane persistence tables."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AirbyteConnectorRow(Base, ProjectScopedMixin):
    """AQP-curated or discovered Airbyte connector definition."""

    __tablename__ = "airbyte_connectors"

    id = Column(String(36), primary_key=True, default=_uuid)
    connector_id = Column(String(160), nullable=False, unique=True, index=True)
    name = Column(String(240), nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    runtime = Column(String(32), nullable=False, default="hybrid", index=True)
    service = Column(String(120), nullable=True, index=True)
    airbyte_definition_id = Column(String(120), nullable=True, index=True)
    docker_repository = Column(String(240), nullable=True)
    docker_image_tag = Column(String(120), nullable=True)
    python_package = Column(String(240), nullable=True)
    docs_url = Column(String(512), nullable=True)
    config_schema = Column(JSON, default=dict)
    streams = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    capabilities = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AirbyteConnectionRow(Base, ProjectScopedMixin):
    """Configured source -> destination connection managed by AQP."""

    __tablename__ = "airbyte_connections"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False, index=True)
    source_connector_id = Column(String(160), nullable=False, index=True)
    destination_connector_id = Column(String(160), nullable=False, index=True)
    airbyte_source_id = Column(String(120), nullable=True, index=True)
    airbyte_destination_id = Column(String(120), nullable=True, index=True)
    airbyte_connection_id = Column(String(120), nullable=True, unique=True, index=True)
    namespace = Column(String(120), nullable=False, default="aqp_airbyte", index=True)
    source_config = Column(JSON, default=dict)
    destination_config = Column(JSON, default=dict)
    catalog = Column(JSON, default=dict)
    streams = Column(JSON, default=list)
    entity_mappings = Column(JSON, default=list)
    materialization_manifest = Column(JSON, nullable=True)
    schedule = Column(JSON, default=dict)
    compute_backend = Column(String(32), nullable=False, default="auto")
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_sync_status = Column(String(32), nullable=True, index=True)
    last_sync_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("namespace", "name", name="uq_airbyte_connections_ns_name"),
    )


class AirbyteSyncRunRow(Base, ProjectScopedMixin):
    """One Airbyte job or embedded read invocation."""

    __tablename__ = "airbyte_sync_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    connection_id = Column(
        String(36),
        ForeignKey("airbyte_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pipeline_run_id = Column(
        String(36),
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    manifest_id = Column(
        String(36),
        ForeignKey("pipeline_manifests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id = Column(String(120), nullable=True, index=True)
    airbyte_job_id = Column(String(120), nullable=True, index=True)
    airbyte_connection_id = Column(String(120), nullable=True, index=True)
    runtime = Column(String(32), nullable=False, default="full_airbyte", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Float, nullable=True)
    records_synced = Column(Integer, nullable=False, default=0)
    bytes_synced = Column(Integer, nullable=False, default=0)
    streams = Column(JSON, default=list)
    cursor_state = Column(JSON, default=dict)
    payload = Column(JSON, default=dict)
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_airbyte_sync_runs_conn_status", "connection_id", "status"),
    )


__all__ = [
    "AirbyteConnectionRow",
    "AirbyteConnectorRow",
    "AirbyteSyncRunRow",
]
