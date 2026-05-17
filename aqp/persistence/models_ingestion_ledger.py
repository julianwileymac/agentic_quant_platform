"""Ingestion ledger + fabric version snapshot ORM models."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from aqp.persistence.models import Base, _uuid

logger = logging.getLogger(__name__)

_JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


class IngestionLedgerRow(Base):
    __tablename__ = "ingestion_ledger"

    id = Column(String(36), primary_key=True, default=_uuid)
    fabric_uuid = Column(String(36), nullable=False, index=True)
    # Logical run identifier; retries may share a fabric_uuid.
    data_source_id = Column(
        String(36),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fetcher_run_id = Column(
        String(36),
        ForeignKey("fetcher_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_hash = Column(String(64), nullable=False, index=True)
    # SHA-256(data_source_id + sorted(catalog_feed_edge_ids) + requested_time_window)
    requested_time_window = Column(String(100), nullable=True)
    execution_start = Column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
    )
    execution_end = Column(DateTime(timezone=False), nullable=True)
    records_extracted = Column(Integer, default=0, nullable=False)
    records_persisted = Column(Integer, default=0, nullable=False)
    execution_status = Column(
        Enum(
            "PENDING",
            "RUNNING",
            "SUCCESS",
            "PARTIAL_FAILURE",
            "FATAL_ERROR",
            name="ingestion_execution_status_enum",
        ),
        nullable=False,
        default="PENDING",
        index=True,
    )
    error_traceback = Column(Text, nullable=True)
    otel_trace_id = Column(String(32), nullable=True)
    otel_span_id = Column(String(16), nullable=True)
    lineage_snapshot = Column(_JSONB_COMPAT, nullable=True)
    business_metadata = Column(_JSONB_COMPAT, nullable=True)
    # medallion_layer / namespace / table_name / owner / tags
    schema_version = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        Index(
            "ix_ingestion_ledger_request_hash_status",
            "request_hash",
            "execution_status",
        ),
        Index(
            "ix_ingestion_ledger_data_source_started",
            "data_source_id",
            "execution_start",
        ),
    )

    data_source = relationship("DataSource")
    fetcher_run = relationship("FetcherRun")


class FabricVersionSnapshot(Base):
    __tablename__ = "fabric_version_snapshots"

    id = Column(String(36), primary_key=True, default=_uuid)
    fabric_uuid = Column(String(36), nullable=False, index=True)
    # App-side discriminator; e.g. instrument_catalog / catalog_feed_edge.
    object_kind = Column(String(64), nullable=False, index=True)
    # Mirror of FabricIdentity.version_vector at snapshot time.
    version_vector = Column(_JSONB_COMPAT, nullable=False)
    # Full FabricSerializerMixin.to_canonical_dict() payload.
    snapshot_data = Column(_JSONB_COMPAT, nullable=False)
    # Computed at write-site by VersionManager.persist_snapshot.
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_fabric_version_snapshots_uuid_created",
            "fabric_uuid",
            "created_at",
        ),
    )


__all__ = ["FabricVersionSnapshot", "IngestionLedgerRow"]
