"""Data control-plane metadata/version tables."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SourceLibraryEntry(Base, ProjectScopedMixin):
    """Editable metadata library entry for a data source."""

    __tablename__ = "source_library_entries"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_id = Column(String(36), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name = Column(String(120), nullable=False, index=True)
    display_name = Column(String(240), nullable=False)
    import_uri = Column(String(1024), nullable=True)
    reference_path = Column(String(1024), nullable=True)
    docs_url = Column(String(1024), nullable=True)
    default_node = Column(String(160), nullable=True)
    metadata_json = Column(JSON, default=dict)
    setup_steps = Column(JSON, default=list)
    pipeline_hints = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "source_name", name="uq_source_library_project_source"),
    )


class SourceMetadataVersion(Base, ProjectScopedMixin):
    """Immutable snapshot of source metadata after every import/edit."""

    __tablename__ = "source_metadata_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_id = Column(String(36), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name = Column(String(120), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    change_kind = Column(String(40), nullable=False, default="edit", index=True)
    import_uri = Column(String(1024), nullable=True)
    reference_path = Column(String(1024), nullable=True)
    docs_url = Column(String(1024), nullable=True)
    metadata_json = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    created_by = Column(String(120), nullable=False, default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_source_metadata_versions_source_version", "source_name", "version"),
    )


class DatasetPipelineConfigRow(Base, ProjectScopedMixin):
    """Versioned project-level dataset pipeline configuration."""

    __tablename__ = "dataset_pipeline_configs"

    id = Column(String(36), primary_key=True, default=_uuid)
    dataset_catalog_id = Column(String(36), ForeignKey("dataset_catalogs.id", ondelete="SET NULL"), nullable=True, index=True)
    manifest_id = Column(String(36), ForeignKey("pipeline_manifests.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(180), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="draft", index=True)
    config_json = Column(JSON, default=dict)
    sinks = Column(JSON, default=list)
    automations = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(120), nullable=False, default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "name", "version", name="uq_dataset_pipeline_config_version"),
        Index("ix_dataset_pipeline_configs_name_active", "name", "is_active"),
    )


__all__ = [
    "DatasetPipelineConfigRow",
    "SourceLibraryEntry",
    "SourceMetadataVersion",
]
