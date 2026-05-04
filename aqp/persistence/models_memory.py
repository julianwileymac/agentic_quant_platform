"""Durable memory tables: episodes, reflections, deferred outcomes.

Working-memory queues live in Redis. Episodes + reflections persist
through both BM25 JSONL files (for cheap recall) **and** these tables
(for SQL-driven analysis and webui rendering).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import LabScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MemoryEpisode(Base, LabScopedMixin):
    """One ``situation -> lesson`` recollection per (role, vt_symbol)."""

    __tablename__ = "memory_episodes"
    id = Column(String(36), primary_key=True, default=_uuid)
    role = Column(String(120), nullable=False, index=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    as_of = Column(DateTime, nullable=True, index=True)
    situation = Column(Text, nullable=False)
    lesson = Column(Text, nullable=False)
    outcome = Column(Float, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MemoryReflection(Base, LabScopedMixin):
    """A post-outcome reflection (TradingAgents-style deferred reflector)."""

    __tablename__ = "memory_reflections"
    id = Column(String(36), primary_key=True, default=_uuid)
    role = Column(String(120), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    vt_symbol = Column(String(64), nullable=True, index=True)
    as_of = Column(DateTime, nullable=True, index=True)
    lesson = Column(Text, nullable=False)
    outcome = Column(Float, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Index(
    "ix_memory_reflection_lookup",
    MemoryReflection.role,
    MemoryReflection.vt_symbol,
    MemoryReflection.created_at,
)


class MemoryOutcome(Base, LabScopedMixin):
    """Resolved outcome paired with its earlier decision (for reflection)."""

    __tablename__ = "memory_outcomes"
    id = Column(String(36), primary_key=True, default=_uuid)
    decision_id = Column(String(60), nullable=False, index=True)
    vt_symbol = Column(String(64), nullable=False, index=True)
    decision_at = Column(DateTime, nullable=True)
    outcome_at = Column(DateTime, nullable=True, index=True)
    raw_return = Column(Float, nullable=True)
    benchmark_return = Column(Float, nullable=True)
    excess_return = Column(Float, nullable=True)
    direction_correct = Column(Float, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "MemoryEpisode",
    "MemoryOutcome",
    "MemoryReflection",
]
