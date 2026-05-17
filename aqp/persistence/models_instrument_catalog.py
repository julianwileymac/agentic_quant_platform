"""Instrument catalog + source-edge ORM models for data fabric phase 1."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from aqp.data.fabric.identity import FabricHashMixin
from aqp.persistence.models import Base, _uuid

logger = logging.getLogger(__name__)

_JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")
_CONTENT_HASH_EXCLUDED_COLUMNS = frozenset(
    {"content_hash", "created_at", "id", "updated_at"}
)


class InstrumentCatalog(Base):
    __tablename__ = "instrument_catalogs"

    id = Column(String(36), primary_key=True, default=_uuid)
    universal_ticker = Column(String(50), nullable=False, index=True)
    asset_class = Column(String(50), nullable=False, index=True)
    # Free-form app-side-validated value; intentionally not a SQL enum.
    exchange_code = Column(String(50), nullable=True, index=True)
    metadata_blob = Column(_JSONB_COMPAT, nullable=True)
    is_actively_traded = Column(Boolean, default=True, nullable=False)
    last_catalog_sync = Column(DateTime(timezone=False), nullable=True)
    content_hash = Column(String(64), nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    promoted_instrument_id = Column(
        String(36),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "universal_ticker",
            "exchange_code",
            name="uq_instrument_catalog_ticker_exchange",
        ),
        Index(
            "ix_instrument_catalog_asset_class_exchange",
            "asset_class",
            "exchange_code",
        ),
        Index(
            "ix_instrument_catalog_metadata_gin",
            "metadata_blob",
            postgresql_using="gin",
        ),
        Index(
            "ix_instrument_catalog_metadata_sector",
            text("(metadata_blob->>'sector')"),
        ),
    )

    edges = relationship(
        "CatalogFeedEdge",
        back_populates="instrument",
        cascade="all, delete-orphan",
    )
    promoted_instrument = relationship(
        "Instrument",
        foreign_keys=[promoted_instrument_id],
    )


class CatalogFeedEdge(Base):
    __tablename__ = "catalog_feed_edges"

    id = Column(String(36), primary_key=True, default=_uuid)
    instrument_catalog_id = Column(
        String(36),
        ForeignKey("instrument_catalogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_source_id = Column(
        String(36),
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_specific_ticker = Column(String(100), nullable=False, index=True)
    # interval / adjust_type / endpoint_path / priority_rank / supported_data_types
    edge_metadata_params = Column(_JSONB_COMPAT, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    content_hash = Column(String(64), nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "instrument_catalog_id",
            "data_source_id",
            "provider_specific_ticker",
            name="uq_catalog_feed_edge",
        ),
    )

    instrument = relationship("InstrumentCatalog", back_populates="edges")
    data_source = relationship("DataSource")


def _build_hash_payload(target: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column in target.__table__.columns:
        if column.name in _CONTENT_HASH_EXCLUDED_COLUMNS:
            continue
        payload[column.name] = getattr(target, column.name)
    return payload


def _set_row_content_hash(target: Any) -> None:
    payload = _build_hash_payload(target)
    target.content_hash = FabricHashMixin.compute_dict_hash(payload)


@event.listens_for(InstrumentCatalog, "before_insert")
@event.listens_for(InstrumentCatalog, "before_update")
def _instrument_catalog_content_hash_listener(
    _mapper: Any,
    _connection: Any,
    target: InstrumentCatalog,
) -> None:
    _set_row_content_hash(target)


@event.listens_for(CatalogFeedEdge, "before_insert")
@event.listens_for(CatalogFeedEdge, "before_update")
def _catalog_feed_edge_content_hash_listener(
    _mapper: Any,
    _connection: Any,
    target: CatalogFeedEdge,
) -> None:
    _set_row_content_hash(target)


__all__ = ["CatalogFeedEdge", "InstrumentCatalog"]
