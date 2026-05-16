"""Research-paper RAG corpus ORM (Alembic 0035).

Companion to :mod:`aqp.rag.indexers.research_papers_indexer` and the
``/rag/papers/*`` REST routes. The PDF itself lives on disk at
``pdf_path``; the row carries the rich metadata + parser audit.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchPaperRow(Base, ProjectScopedMixin):
    """One ingested research paper.

    Each row is immutable from the user's perspective: re-uploading
    the same PDF creates a new row + new ``id``. Edits to metadata
    are allowed (titles can be auto-extracted incorrectly).
    """

    __tablename__ = "research_papers"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(512), nullable=True)
    authors = Column(JSON, default=list)  # list[str]
    author_institution = Column(String(256), nullable=True, index=True)
    publication_year = Column(Integer, nullable=True, index=True)
    source_url = Column(String(1024), nullable=True)
    asset_class = Column(JSON, default=list)  # list[str]
    strategy_family = Column(String(64), nullable=True, index=True)
    contains_mathematics = Column(Boolean, nullable=True)
    equation_count = Column(Integer, default=0)
    pdf_path = Column(String(1024), nullable=True)
    chunk_count = Column(Integer, default=0)
    parser_used = Column(String(32), nullable=True)
    vt_symbol = Column(String(64), nullable=True)
    abstract = Column(Text, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


Index(
    "ix_research_papers_workspace_strategy",
    ResearchPaperRow.workspace_id,
    ResearchPaperRow.strategy_family,
)


__all__ = ["ResearchPaperRow"]
