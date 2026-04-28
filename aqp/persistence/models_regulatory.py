"""Regulatory data ORM models — CFPB, FDA, USPTO.

These tables back the third-order RAG layer ([aqp/rag/orders.py](../rag/orders.py))
and the new ``aqp/data/sources/{cfpb,fda,uspto}`` adapters. Each row
carries an optional ``vt_symbol`` so the indexers can scope retrievals
by instrument when an issuer linkage exists.

All Iceberg writes for the same data also pass through
``aqp.data.iceberg_catalog.append_arrow``; these Postgres tables hold
the curated, query-friendly view used by the API and webui.
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
    Index,
    Integer,
    String,
    Text,
)

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------- CFPB
class CfpbComplaint(Base):
    """One row per CFPB Consumer Complaint Database submission."""

    __tablename__ = "cfpb_complaints"
    id = Column(String(36), primary_key=True, default=_uuid)
    complaint_id = Column(String(40), nullable=False, unique=True, index=True)
    company = Column(String(240), nullable=False, index=True)
    company_response = Column(String(120), nullable=True)
    consumer_consent_provided = Column(String(40), nullable=True)
    consumer_complaint_narrative = Column(Text, nullable=True)
    date_received = Column(DateTime, nullable=True, index=True)
    date_sent_to_company = Column(DateTime, nullable=True)
    issue = Column(String(240), nullable=True, index=True)
    sub_issue = Column(String(240), nullable=True)
    product = Column(String(120), nullable=True, index=True)
    sub_product = Column(String(120), nullable=True)
    state = Column(String(8), nullable=True)
    zip_code = Column(String(16), nullable=True)
    submitted_via = Column(String(40), nullable=True)
    tags = Column(String(240), nullable=True)
    timely = Column(String(8), nullable=True)
    has_narrative = Column(Boolean, nullable=False, default=False)
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index("ix_cfpb_company_date", CfpbComplaint.company, CfpbComplaint.date_received)


# ---------------------------------------------------------------------- FDA
class FdaApplication(Base):
    """FDA drug + device application (NDA, ANDA, BLA, 510(k), PMA, ...)."""

    __tablename__ = "fda_applications"
    id = Column(String(36), primary_key=True, default=_uuid)
    application_number = Column(String(40), nullable=False, unique=True, index=True)
    application_type = Column(String(20), nullable=True, index=True)
    sponsor_name = Column(String(240), nullable=False, index=True)
    drug_name = Column(String(240), nullable=True, index=True)
    indication = Column(Text, nullable=True)
    submission_status = Column(String(60), nullable=True)
    submission_date = Column(DateTime, nullable=True, index=True)
    approval_date = Column(DateTime, nullable=True)
    review_priority = Column(String(40), nullable=True)
    therapeutic_area = Column(String(120), nullable=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FdaAdverseEvent(Base):
    """FAERS / MAUDE adverse-event report (one per event)."""

    __tablename__ = "fda_adverse_events"
    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(60), nullable=False, unique=True, index=True)
    received_date = Column(DateTime, nullable=True, index=True)
    product_name = Column(String(240), nullable=True, index=True)
    manufacturer_name = Column(String(240), nullable=True, index=True)
    reactions = Column(Text, nullable=True)
    outcomes = Column(Text, nullable=True)
    is_serious = Column(Boolean, nullable=True)
    patient_age = Column(Float, nullable=True)
    patient_sex = Column(String(10), nullable=True)
    country = Column(String(40), nullable=True)
    source = Column(String(20), nullable=True)  # faers | maude
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FdaRecall(Base):
    """FDA enforcement recall (Class I/II/III)."""

    __tablename__ = "fda_recalls"
    id = Column(String(36), primary_key=True, default=_uuid)
    recall_number = Column(String(60), nullable=False, unique=True, index=True)
    recalling_firm = Column(String(240), nullable=False, index=True)
    classification = Column(String(20), nullable=True, index=True)
    status = Column(String(40), nullable=True)
    product_description = Column(Text, nullable=True)
    reason_for_recall = Column(Text, nullable=True)
    code_info = Column(Text, nullable=True)
    distribution_pattern = Column(Text, nullable=True)
    voluntary_mandated = Column(String(60), nullable=True)
    initial_firm_notification = Column(String(120), nullable=True)
    recall_initiation_date = Column(DateTime, nullable=True, index=True)
    report_date = Column(DateTime, nullable=True)
    termination_date = Column(DateTime, nullable=True)
    product_type = Column(String(40), nullable=True)  # drug | device | food
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------- USPTO
class UsptoPatent(Base):
    """USPTO granted patent."""

    __tablename__ = "uspto_patents"
    id = Column(String(36), primary_key=True, default=_uuid)
    patent_number = Column(String(40), nullable=False, unique=True, index=True)
    title = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    filing_date = Column(DateTime, nullable=True, index=True)
    grant_date = Column(DateTime, nullable=True, index=True)
    assignee = Column(String(240), nullable=True, index=True)
    inventors = Column(JSON, default=list)
    classification = Column(String(120), nullable=True)
    application_number = Column(String(60), nullable=True, index=True)
    citation_count = Column(Integer, nullable=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UsptoTrademark(Base):
    """USPTO trademark application / registration."""

    __tablename__ = "uspto_trademarks"
    id = Column(String(36), primary_key=True, default=_uuid)
    serial_number = Column(String(40), nullable=False, unique=True, index=True)
    registration_number = Column(String(40), nullable=True, index=True)
    mark_text = Column(String(480), nullable=True)
    owner = Column(String(240), nullable=True, index=True)
    status = Column(String(60), nullable=True, index=True)
    filing_date = Column(DateTime, nullable=True, index=True)
    registration_date = Column(DateTime, nullable=True)
    abandonment_date = Column(DateTime, nullable=True)
    class_codes = Column(String(240), nullable=True)
    description = Column(Text, nullable=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UsptoAssignment(Base):
    """USPTO patent assignment recordation."""

    __tablename__ = "uspto_assignments"
    id = Column(String(36), primary_key=True, default=_uuid)
    assignment_id = Column(String(60), nullable=False, unique=True, index=True)
    recorded_date = Column(DateTime, nullable=True, index=True)
    execution_date = Column(DateTime, nullable=True)
    conveyance_text = Column(String(240), nullable=True)
    assignor = Column(String(240), nullable=True, index=True)
    assignee = Column(String(240), nullable=True, index=True)
    patents = Column(Text, nullable=True)  # comma-separated patent numbers
    vt_symbol = Column(String(64), nullable=True, index=True)
    raw = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "CfpbComplaint",
    "FdaAdverseEvent",
    "FdaApplication",
    "FdaRecall",
    "UsptoAssignment",
    "UsptoPatent",
    "UsptoTrademark",
]
