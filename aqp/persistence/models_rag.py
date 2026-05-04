"""ORM rows that mirror Redis-RAG state for SQL queries.

Redis is the source of truth for vectors + tag indexes; these tables
hold lightweight summaries the API and webui can paginate / filter on
(corpus stats, query audit, eval runs).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import LabScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RagCorpus(Base, LabScopedMixin):
    """One row per registered corpus (mirror of :data:`OrderCatalog`)."""

    __tablename__ = "rag_corpora"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(120), nullable=False, unique=True, index=True)
    order = Column(String(20), nullable=False, index=True)
    l1 = Column(String(80), nullable=False, index=True)
    l2 = Column(String(80), nullable=False, default="")
    iceberg_identifier = Column(String(240), nullable=True)
    description = Column(Text, nullable=True)
    chunks_count = Column(Integer, nullable=False, default=0)
    last_indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RagDocument(Base, LabScopedMixin):
    """Optional source-document metadata kept in Postgres for quick joins."""

    __tablename__ = "rag_documents"
    id = Column(String(36), primary_key=True, default=_uuid)
    corpus = Column(String(120), nullable=False, index=True)
    source_id = Column(String(240), nullable=False, index=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    as_of = Column(DateTime, nullable=True, index=True)
    chunk_count = Column(Integer, nullable=False, default=0)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RagChunkAudit(Base, LabScopedMixin):
    """Sample chunk metadata kept for inspection (full text lives in Redis)."""

    __tablename__ = "rag_chunks"
    id = Column(String(36), primary_key=True, default=_uuid)
    corpus = Column(String(120), nullable=False, index=True)
    level = Column(String(8), nullable=False, index=True)
    doc_id = Column(String(240), nullable=False, index=True)
    chunk_idx = Column(Integer, nullable=False, default=0)
    vt_symbol = Column(String(64), nullable=True, index=True)
    as_of = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RagSummary(Base, LabScopedMixin):
    """Raptor summary node (parent over a cluster of leaf chunks)."""

    __tablename__ = "rag_summaries"
    id = Column(String(36), primary_key=True, default=_uuid)
    corpus = Column(String(120), nullable=False, index=True)
    level = Column(String(8), nullable=False, index=True)
    raptor_level = Column(Integer, nullable=False, default=1)
    cluster_id = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    member_ids = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RagQuery(Base, LabScopedMixin):
    """Audit log of every retrieval (used by /rag/explorer)."""

    __tablename__ = "rag_queries"
    id = Column(String(36), primary_key=True, default=_uuid)
    query = Column(Text, nullable=False)
    plan_level = Column(String(20), nullable=False, default="walk")
    plan_corpus = Column(String(120), nullable=False, default="*")
    results = Column(JSON, default=list)
    result_count = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class RagEvalRun(Base, LabScopedMixin):
    """Outcome of a RAG evaluation pass."""

    __tablename__ = "rag_eval_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False, default="adhoc")
    level = Column(String(8), nullable=False, default="l3")
    k = Column(Integer, nullable=False, default=8)
    n_queries = Column(Integer, nullable=False, default=0)
    results = Column(JSON, default=list)
    aggregate = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "RagChunkAudit",
    "RagCorpus",
    "RagDocument",
    "RagEvalRun",
    "RagQuery",
    "RagSummary",
]
