"""Corporate entity graph tables.

Tables:

- ``issuers`` — corporate / government / fund / other entity master.
- ``corporate_entities`` — polymorphic sidecar for corporate-specific fields.
- ``entity_relationships`` — directed edges (parent/subsidiary/listing_agent/…).
- ``industry_classifications`` — per-entity (scheme, code, label, level).
- ``sectors`` + ``industries`` — authoritative GICS/TRBC/ICB tables.
- ``locations`` — per-entity physical locations (HQ, mailing, regional).
- ``key_executives`` + ``executive_compensation`` — officers and pay.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class Issuer(Base):
    """Polymorphic issuer row.

    ``kind`` discriminates between ``corporate`` / ``government`` /
    ``municipal`` / ``supranational`` / ``central_bank`` / ``fund`` /
    ``index_administrator`` / ``individual`` / ``other``. Corporate-specific
    columns live on :class:`CorporateEntity` via joined-table inheritance;
    simple rows can store everything here.
    """

    __tablename__ = "issuers"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False, index=True)
    legal_name = Column(String(240), nullable=True)
    kind = Column(String(32), nullable=False, default="corporate", index=True)

    cik = Column(String(16), nullable=True, index=True)
    lei = Column(String(20), nullable=True, unique=True, index=True)
    cusip = Column(String(16), nullable=True, index=True)
    isin = Column(String(16), nullable=True, index=True)
    figi = Column(String(16), nullable=True, index=True)
    permid = Column(String(32), nullable=True, index=True)
    gvkey = Column(String(16), nullable=True, index=True)
    irs_ein = Column(String(16), nullable=True)

    entity_legal_form = Column(String(120), nullable=True)
    entity_status = Column(String(32), nullable=True)
    inc_state = Column(String(64), nullable=True)
    inc_country = Column(String(64), nullable=True)
    stock_exchange = Column(String(120), nullable=True)
    primary_listing = Column(String(64), nullable=True)
    currency = Column(String(16), nullable=True)
    is_listed = Column(Boolean, default=True)
    country = Column(String(64), nullable=True)
    employees = Column(Integer, nullable=True)

    sic = Column(Integer, nullable=True, index=True)
    naics = Column(String(16), nullable=True, index=True)
    sector_id = Column(String(36), ForeignKey("sectors.id"), nullable=True, index=True)
    industry_id = Column(String(36), ForeignKey("industries.id"), nullable=True, index=True)

    short_description = Column(Text, nullable=True)
    long_description = Column(Text, nullable=True)
    company_url = Column(String(512), nullable=True)
    template = Column(String(120), nullable=True)
    ceo = Column(String(240), nullable=True)

    latest_filing_date = Column(Date, nullable=True)
    first_fundamental_date = Column(Date, nullable=True)
    last_fundamental_date = Column(Date, nullable=True)
    first_stock_price_date = Column(Date, nullable=True)
    last_stock_price_date = Column(Date, nullable=True)

    identifiers = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __mapper_args__ = {
        "polymorphic_on": kind,
        "polymorphic_identity": "corporate",
        "with_polymorphic": "*",
    }


class GovernmentEntity(Issuer):
    __tablename__ = "government_entities"
    id = Column(String(36), ForeignKey("issuers.id"), primary_key=True)
    jurisdiction = Column(String(120), nullable=True)
    credit_rating_sp = Column(String(16), nullable=True)
    credit_rating_moodys = Column(String(16), nullable=True)
    credit_rating_fitch = Column(String(16), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "government"}


class Fund(Issuer):
    __tablename__ = "fund_issuers"
    id = Column(String(36), ForeignKey("issuers.id"), primary_key=True)
    fund_family = Column(String(240), nullable=True)
    manager = Column(String(240), nullable=True)
    aum = Column(Float, nullable=True)
    inception = Column(Date, nullable=True)
    fund_type = Column(String(32), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "fund"}


class Sector(Base):
    __tablename__ = "sectors"
    id = Column(String(36), primary_key=True, default=_uuid)
    scheme = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    level = Column(Integer, nullable=False, default=1)
    parent_id = Column(String(36), ForeignKey("sectors.id"), nullable=True)

    __table_args__ = (Index("ix_sectors_scheme_code", "scheme", "code", unique=True),)


class Industry(Base):
    __tablename__ = "industries"
    id = Column(String(36), primary_key=True, default=_uuid)
    scheme = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    sector_id = Column(String(36), ForeignKey("sectors.id"), nullable=True)
    level = Column(Integer, nullable=False, default=3)
    parent_id = Column(String(36), ForeignKey("industries.id"), nullable=True)

    __table_args__ = (Index("ix_industries_scheme_code", "scheme", "code", unique=True),)


class IndustryClassification(Base):
    """Per-entity classification under a specific scheme.

    An issuer typically has several rows here — one SIC entry, one NAICS
    entry, four GICS entries (sector/group/industry/sub-industry), …
    """

    __tablename__ = "industry_classifications"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=False, index=True)
    scheme = Column(String(16), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    label = Column(String(240), nullable=True)
    level = Column(Integer, nullable=False, default=1)
    parent_code = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_industry_cls_issuer_scheme", "issuer_id", "scheme"),
        Index("ix_industry_cls_code", "scheme", "code"),
    )


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"
    id = Column(String(36), primary_key=True, default=_uuid)
    from_kind = Column(String(32), nullable=False, default="issuer")
    from_entity_id = Column(String(64), nullable=False, index=True)
    to_kind = Column(String(32), nullable=False, default="issuer")
    to_entity_id = Column(String(64), nullable=False, index=True)
    relationship_type = Column(String(32), nullable=False, index=True)
    ownership_pct = Column(Float, nullable=True)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    source = Column(String(64), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_rel_from_to_type", "from_entity_id", "to_entity_id", "relationship_type"),
    )


class Location(Base):
    __tablename__ = "locations"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=False, index=True)
    country = Column(String(64), nullable=True)
    country_iso = Column(String(8), nullable=True)
    region = Column(String(64), nullable=True)
    state = Column(String(64), nullable=True)
    city = Column(String(120), nullable=True)
    postal_code = Column(String(16), nullable=True)
    address_line1 = Column(String(240), nullable=True)
    address_line2 = Column(String(240), nullable=True)
    phone = Column(String(48), nullable=True)
    is_headquarters = Column(Boolean, default=False)
    is_mailing = Column(Boolean, default=False)
    meta = Column(JSON, default=dict)


class KeyExecutive(Base):
    __tablename__ = "key_executives"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=False, index=True)
    name = Column(String(240), nullable=False)
    title = Column(String(240), nullable=False)
    tenure_start = Column(Date, nullable=True)
    tenure_end = Column(Date, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(16), nullable=True)
    compensation = Column(Float, nullable=True)
    compensation_currency = Column(String(16), nullable=True)
    bio = Column(Text, nullable=True)
    fiscal_year = Column(Integer, nullable=True)


class ExecutiveCompensation(Base):
    __tablename__ = "executive_compensation"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=False, index=True)
    executive_name = Column(String(240), nullable=False)
    title = Column(String(240), nullable=True)
    fiscal_year = Column(Integer, nullable=True, index=True)
    salary = Column(Float, nullable=True)
    bonus = Column(Float, nullable=True)
    stock_awards = Column(Float, nullable=True)
    option_awards = Column(Float, nullable=True)
    non_equity_incentives = Column(Float, nullable=True)
    pension = Column(Float, nullable=True)
    other_compensation = Column(Float, nullable=True)
    total = Column(Float, nullable=True)
    currency = Column(String(16), default="USD")

    __table_args__ = (
        Index("ix_exec_comp_issuer_year", "issuer_id", "fiscal_year"),
    )
