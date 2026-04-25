"""News persistence tables (news items, entity M2M, sentiment)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
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


class NewsItemRow(Base):
    __tablename__ = "news_items"
    id = Column(String(36), primary_key=True, default=_uuid)
    news_id = Column(String(120), nullable=True, unique=True, index=True)
    headline = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    url = Column(String(1024), nullable=True)
    publisher = Column(String(120), nullable=True, index=True)
    author = Column(String(240), nullable=True)
    language = Column(String(16), default="en")
    region = Column(String(64), nullable=True)
    country = Column(String(64), nullable=True)
    image_url = Column(String(1024), nullable=True)
    published_ts = Column(DateTime, nullable=True, index=True)
    collected_ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    tags = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    event_type = Column(String(32), nullable=True)  # macro | geopolitical | company | sector
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String(32), nullable=True, index=True)
    provider = Column(String(64), nullable=True, index=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_news_pub_ts", "published_ts"),
    )


class NewsItemEntity(Base):
    """M2M link between ``news_items`` and ``instruments`` / ``issuers``.

    One row per ``(news_item, entity)`` pair. ``entity_kind`` = ``instrument``
    or ``issuer``. ``relevance_score`` is a provider-supplied confidence
    that the article is actually about the entity.
    """

    __tablename__ = "news_item_entities"
    id = Column(String(36), primary_key=True, default=_uuid)
    news_item_id = Column(
        String(36),
        ForeignKey("news_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_kind = Column(String(32), nullable=False, default="instrument", index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    relevance_score = Column(Float, nullable=True)

    __table_args__ = (
        Index("uq_news_entity", "news_item_id", "entity_kind", "entity_id", unique=True),
    )


class NewsSentiment(Base):
    """Per-news-item sentiment evaluation by a named model.

    Multiple rows per news item allowed — one per evaluator (FinBERT,
    OpenAI, VADER, crowd).
    """

    __tablename__ = "news_sentiments"
    id = Column(String(36), primary_key=True, default=_uuid)
    news_item_id = Column(
        String(36),
        ForeignKey("news_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model = Column(String(120), nullable=False)
    model_version = Column(String(32), nullable=True)
    score = Column(Float, nullable=True)
    label = Column(String(32), nullable=True, index=True)
    confidence = Column(Float, nullable=True)
    raw = Column(JSON, default=dict)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_news_sent_item_model", "news_item_id", "model"),
    )
