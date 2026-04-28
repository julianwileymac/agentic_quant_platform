"""dbt metadata tables for the local modeling foundation."""
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

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DbtProjectRow(Base):
    """One dbt project known to AQP."""

    __tablename__ = "dbt_projects"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, index=True)
    project_dir = Column(String(1024), nullable=False)
    profiles_dir = Column(String(1024), nullable=False)
    target = Column(String(80), nullable=False, default="dev", index=True)
    adapter = Column(String(80), nullable=False, default="duckdb", index=True)
    duckdb_path = Column(String(1024), nullable=True)
    generated_schema = Column(String(120), nullable=True)
    generated_tag = Column(String(120), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "project_dir", name="uq_dbt_projects_name_dir"),
    )


class DbtModelVersionRow(Base):
    """Manifest snapshot for a dbt model/source/seed."""

    __tablename__ = "dbt_model_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(
        String(36),
        ForeignKey("dbt_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    unique_id = Column(String(512), nullable=False, index=True)
    name = Column(String(240), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False, index=True)
    package_name = Column(String(160), nullable=True)
    original_file_path = Column(String(1024), nullable=True)
    database = Column(String(240), nullable=True)
    schema = Column(String(240), nullable=True)
    alias = Column(String(240), nullable=True)
    materialized = Column(String(64), nullable=True)
    checksum = Column(String(120), nullable=True, index=True)
    tags = Column(JSON, default=list)
    depends_on = Column(JSON, default=list)
    columns = Column(JSON, default=list)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dbt_model_versions_lookup", "project_id", "unique_id"),
    )


class DbtSourceMappingRow(Base):
    """Link generated dbt sources/models back to AQP datasets or tables."""

    __tablename__ = "dbt_source_mappings"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(
        String(36),
        ForeignKey("dbt_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    dbt_unique_id = Column(String(512), nullable=False, index=True)
    source_kind = Column(String(80), nullable=False, index=True)
    source_name = Column(String(512), nullable=False, index=True)
    dataset_catalog_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    iceberg_identifier = Column(String(240), nullable=True, index=True)
    storage_uri = Column(String(1024), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "dbt_unique_id",
            "source_kind",
            "source_name",
            name="uq_dbt_source_mapping",
        ),
    )


class DbtRunRow(Base):
    """One dbt command invocation tracked by AQP."""

    __tablename__ = "dbt_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(
        String(36),
        ForeignKey("dbt_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    command = Column(String(80), nullable=False, index=True)
    selector = Column(JSON, default=list)
    status = Column(String(32), nullable=False, default="running", index=True)
    success = Column(Boolean, nullable=False, default=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Float, nullable=True)
    artifacts = Column(JSON, default=dict)
    args = Column(JSON, default=list)
    run_results = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    models_count = Column(Integer, nullable=False, default=0)
    triggered_by = Column(String(120), nullable=True, index=True)


__all__ = [
    "DbtModelVersionRow",
    "DbtProjectRow",
    "DbtRunRow",
    "DbtSourceMappingRow",
]
