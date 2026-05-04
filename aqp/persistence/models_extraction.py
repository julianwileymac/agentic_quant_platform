"""ORM models for the inspiration-rehydration tables.

- :class:`DatasetPresetRow` mirrors :data:`aqp.data.dataset_presets.PRESETS`
  on disk so the UI can list/filter presets without loading the Python
  registry.
- :class:`ExtractionAuditRow` records each extracted asset (which source
  repo it came from, when it was extracted, current status). Used by the
  ``/data/datasets/library`` and ``/learn`` UI surfaces.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base, _uuid


class DatasetPresetRow(Base, ProjectScopedMixin):
    __tablename__ = "dataset_presets"

    name = Column(String(120), primary_key=True)
    description = Column(Text, nullable=False, default="")
    namespace = Column(String(120), nullable=False)
    table_name = Column(String(160), nullable=False)
    source_kind = Column(String(80), nullable=False)
    ingestion_task = Column(String(240), nullable=False)
    requires_api_key = Column(Boolean, nullable=False, default=False)
    api_key_env_var = Column(String(120), nullable=True)
    default_symbols = Column(JSON, nullable=True)
    interval = Column(String(24), nullable=False, default="1d")
    schedule_cron = Column(String(80), nullable=True)
    documentation_url = Column(String(1024), nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_dataset_presets_namespace", DatasetPresetRow.namespace)
Index("ix_dataset_presets_source_kind", DatasetPresetRow.source_kind)


class ExtractionAuditRow(Base, ProjectScopedMixin):
    __tablename__ = "extraction_audit"

    id = Column(String(36), primary_key=True, default=_uuid)
    asset_alias = Column(String(200), nullable=False, index=True)
    asset_kind = Column(String(60), nullable=False, index=True)  # strategy / model / agent / indicator / tool
    source_repo = Column(String(200), nullable=False, index=True)
    source_path = Column(String(1024), nullable=True)
    status = Column(String(40), nullable=False, default="active")  # active / deprecated / pending
    notes = Column(Text, nullable=True)
    extracted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = ["DatasetPresetRow", "ExtractionAuditRow"]
