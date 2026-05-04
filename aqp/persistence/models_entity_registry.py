"""Unified entity registry tables.

The existing :mod:`aqp.persistence.models_entities` owns the
*structured* entity graph (Issuer, Sector, Industry, KeyExecutive,
…). The unified entity registry built on top is generic: any record
extracted from a dataset (company, product, drug, patent, person,
location) lives here. Extractors populate the rows; LLM enrichers
attach descriptions / relations without mutating raw data.
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

from aqp.persistence._tenancy_mixins import LabScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class EntityRow(Base):
    """One generic entity in the unified registry.

    ``kind`` is the entity discriminator (``company``, ``product``,
    ``drug``, ``patent``, ``person``, ``location``, ``security``,
    ``regulator``, ``concept``). ``canonical_name`` is the human
    label; ``primary_identifier`` is the most authoritative ID we
    have (CIK, ISIN, NDA number, patent number, etc.).
    """

    __tablename__ = "entities"
    id = Column(String(36), primary_key=True, default=_uuid)
    kind = Column(String(64), nullable=False, index=True)
    canonical_name = Column(String(512), nullable=False, index=True)
    short_name = Column(String(240), nullable=True, index=True)
    primary_identifier = Column(String(240), nullable=True, index=True)
    primary_identifier_scheme = Column(String(64), nullable=True, index=True)
    instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    issuer_id = Column(
        String(36),
        ForeignKey("issuers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description = Column(Text, nullable=True)
    attributes = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    confidence = Column(Float, nullable=True)
    source_dataset = Column(String(240), nullable=True, index=True)
    source_extractor = Column(String(120), nullable=True, index=True)
    is_canonical = Column(Boolean, nullable=False, default=True)
    parent_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_entities_kind_name", "kind", "canonical_name"),
    )


class EntityIdentifier(Base):
    """One ``(scheme, value)`` alias for an entity."""

    __tablename__ = "entity_identifiers"
    id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheme = Column(String(64), nullable=False, index=True)
    value = Column(String(512), nullable=False, index=True)
    source = Column(String(120), nullable=True)
    confidence = Column(Float, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_id", "scheme", "value", name="uq_entity_identifier_triple"),
    )


class EntityRelation(Base):
    """A typed edge between two entities."""

    __tablename__ = "entity_relations"
    id = Column(String(36), primary_key=True, default=_uuid)
    subject_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    predicate = Column(String(120), nullable=False, index=True)
    object_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    confidence = Column(Float, nullable=True)
    provenance = Column(String(240), nullable=True, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    properties = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EntityAnnotation(Base, LabScopedMixin):
    """LLM- or human-authored note attached to an entity."""

    __tablename__ = "entity_annotations"
    id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(64), nullable=False, default="description", index=True)
    content = Column(Text, nullable=False)
    author = Column(String(120), nullable=True, index=True)
    model = Column(String(120), nullable=True, index=True)
    provider = Column(String(120), nullable=True)
    citations = Column(JSON, default=list)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EntityDatasetLink(Base):
    """Link an entity to a dataset (and optionally a row range)."""

    __tablename__ = "entity_dataset_links"
    id = Column(String(36), primary_key=True, default=_uuid)
    entity_id = Column(
        String(36),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_catalog_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    dataset_version_id = Column(
        String(36),
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    iceberg_identifier = Column(String(240), nullable=True, index=True)
    row_count = Column(Integer, nullable=True)
    coverage_start = Column(DateTime, nullable=True)
    coverage_end = Column(DateTime, nullable=True)
    role = Column(String(64), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "EntityAnnotation",
    "EntityDatasetLink",
    "EntityIdentifier",
    "EntityRelation",
    "EntityRow",
]
