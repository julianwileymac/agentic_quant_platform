"""Data engine pipeline tables.

Stores declarative manifests, materialized run history, profile cache
mirrors, datahub sync log, and per-fetcher invocation log. Engine
authors interact with this through helper modules in
:mod:`aqp.data.engine` and :mod:`aqp.data.profiling`; route handlers
read these directly for the ``/data/engine``, ``/data/datahub``, and
``/datasets/.../profile`` UI surfaces.
"""
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


class PipelineManifestRow(Base, ProjectScopedMixin):
    """Persisted :class:`aqp.data.engine.PipelineManifest`."""

    __tablename__ = "pipeline_manifests"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, index=True)
    namespace = Column(String(120), nullable=False, default="aqp", index=True)
    description = Column(Text, nullable=True)
    owner = Column(String(120), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    spec_json = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    compute_backend = Column(String(32), nullable=True, index=True)
    schedule_cron = Column(String(120), nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("namespace", "name", name="uq_pipeline_manifests_ns_name"),
    )


class PipelineRunRow(Base, ProjectScopedMixin):
    """One execution of a :class:`PipelineManifestRow`."""

    __tablename__ = "pipeline_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    manifest_id = Column(
        String(36),
        ForeignKey("pipeline_manifests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    namespace = Column(String(120), nullable=False, default="aqp", index=True)
    name = Column(String(160), nullable=False, index=True)
    backend = Column(String(32), nullable=False, default="local")
    status = Column(String(32), nullable=False, default="running", index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    rows_written = Column(Integer, nullable=False, default=0)
    tables_written = Column(Integer, nullable=False, default=0)
    sink_result = Column(JSON, default=dict)
    lineage = Column(JSON, default=dict)
    errors = Column(JSON, default=list)
    extras = Column(JSON, default=list)
    triggered_by = Column(String(120), nullable=True, index=True)
    dagster_run_id = Column(String(120), nullable=True, index=True)
    code_version_sha = Column(String(64), nullable=True)
    duration_seconds = Column(Float, nullable=True)


class DatasetProfile(Base, ProjectScopedMixin):
    """Cached column statistics for a dataset version."""

    __tablename__ = "dataset_profiles"
    id = Column(String(36), primary_key=True, default=_uuid)
    namespace = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False, index=True)
    version = Column(Integer, nullable=True, index=True)
    rows = Column(Integer, nullable=False, default=0)
    bytes = Column(Integer, nullable=False, default=0)
    columns = Column(JSON, default=list)
    summary = Column(JSON, default=dict)
    engine = Column(String(32), nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_dataset_profiles_lookup", "namespace", "name", "version"),
    )


class DatahubSyncLog(Base, ProjectScopedMixin):
    """One emit / pull cycle against DataHub."""

    __tablename__ = "datahub_sync_log"
    id = Column(String(36), primary_key=True, default=_uuid)
    direction = Column(String(16), nullable=False, default="push")
    target = Column(String(240), nullable=False, index=True)
    urn = Column(String(512), nullable=True, index=True)
    platform = Column(String(64), nullable=True, index=True)
    platform_instance = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="ok", index=True)
    error = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)


class FetcherRun(Base, ProjectScopedMixin):
    """One invocation of a :class:`aqp.data.fetchers.Fetcher`.

    Useful for the ``/data/sources`` UI to display recent activity per
    source without scanning Iceberg manifests.
    """

    __tablename__ = "fetcher_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    source_name = Column(String(120), nullable=False, index=True)
    fetcher_alias = Column(String(160), nullable=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    rows_produced = Column(Integer, nullable=False, default=0)
    bytes_received = Column(Integer, nullable=False, default=0)
    requests = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="ok", index=True)
    error = Column(Text, nullable=True)
    pipeline_run_id = Column(
        String(36),
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extras = Column(JSON, default=dict)


__all__ = [
    "DatahubSyncLog",
    "DatasetProfile",
    "FetcherRun",
    "PipelineManifestRow",
    "PipelineRunRow",
]
