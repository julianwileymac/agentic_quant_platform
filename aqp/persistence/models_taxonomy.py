"""Taxonomy / tagging graph + entity crosswalk tables.

- ``taxonomy_schemes`` — top-level taxonomy catalogs (SIC, NAICS, GICS,
  TRBC, ICB, BICS, plus user-defined ``thematic``, ``region``, ``risk``).
- ``taxonomy_nodes`` — self-referencing tree of nodes inside a scheme.
- ``entity_tags`` — polymorphic many-to-many linking any entity_kind
  (instrument, issuer, fund, filing, news, series…) to a taxonomy_node.
- ``entity_crosswalk`` — resolved M:N between two identifier-keyed
  entities across ingestion sources (e.g. FRED series ↔ FRB H.15 table).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from aqp.persistence.models import Base, _uuid


class TaxonomyScheme(Base):
    __tablename__ = "taxonomy_schemes"
    id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String(32), nullable=False, unique=True, index=True)
    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    level_labels = Column(JSON, default=list)
    is_user_defined = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"
    id = Column(String(36), primary_key=True, default=_uuid)
    scheme_id = Column(String(36), ForeignKey("taxonomy_schemes.id"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("taxonomy_nodes.id"), nullable=True, index=True)
    code = Column(String(64), nullable=False, index=True)
    label = Column(String(240), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    path = Column(String(1024), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_tax_node_scheme_code", "scheme_id", "code", unique=True),
        Index("ix_tax_node_path", "path"),
    )


class EntityTag(Base):
    """Polymorphic tag application.

    Links any (``entity_kind``, ``entity_id``) pair to a
    :class:`TaxonomyNode`. ``entity_kind`` is one of ``instrument`` /
    ``issuer`` / ``fund`` / ``filing`` / ``news`` / ``series`` / ``strategy``
    / ``backtest`` / ``custom``.
    """

    __tablename__ = "entity_tags"
    id = Column(String(36), primary_key=True, default=_uuid)
    entity_kind = Column(String(32), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    taxonomy_node_id = Column(
        String(36),
        ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheme_code = Column(String(32), nullable=True, index=True)  # denormalized
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(64), nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_entity_tag", "entity_kind", "entity_id", "taxonomy_node_id", unique=True),
        Index("ix_tag_scheme", "scheme_code"),
    )


class EntityCrosswalk(Base):
    """Generic M:N crosswalk between two entities across sources.

    Example uses: FRED DGS10 ↔ FRB H.15 table row; OpenFIGI share_class
    ↔ SEC CIK ↔ Bloomberg parsekyable_des; GDelt theme ↔ GICS industry.
    Keeps mapping logic explicit (queryable) rather than buried in code.
    """

    __tablename__ = "entity_crosswalk"
    id = Column(String(36), primary_key=True, default=_uuid)
    from_kind = Column(String(32), nullable=False, index=True)
    from_value = Column(String(240), nullable=False, index=True)
    to_kind = Column(String(32), nullable=False, index=True)
    to_value = Column(String(240), nullable=False, index=True)
    relationship = Column(String(32), nullable=False, default="equivalent")
    confidence = Column(Float, nullable=False, default=1.0)
    source = Column(String(64), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_crosswalk",
            "from_kind",
            "from_value",
            "to_kind",
            "to_value",
            "relationship",
            unique=True,
        ),
    )
