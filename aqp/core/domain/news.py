"""News + sentiment primitives.

Canonical shapes for the :mod:`aqp.data.news` pipeline and the OpenBB-parity
``company_news`` / ``world_news`` standard_models. Sentiment is first-class
so LLM enrichment results can travel with the raw item.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SentimentLabel(StrEnum):
    """Coarse sentiment classification used throughout the platform."""

    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"
    UNKNOWN = "unknown"


class Sentiment(BaseModel):
    """A sentiment evaluation produced by a named model."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    score: float | None = Field(default=None, description="Continuous score, convention: [-1, 1].")
    label: SentimentLabel = SentimentLabel.UNKNOWN
    model: str | None = None  # e.g. finbert-tone, openai-gpt-4o, vader
    model_version: str | None = None
    ts: datetime | None = None
    confidence: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NewsItem(BaseModel):
    """A single news article / headline."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    news_id: str | None = None
    headline: str = ""
    summary: str | None = None
    body: str | None = None
    url: str | None = None
    publisher: str | None = None
    author: str | None = None
    published_ts: datetime | None = None
    collected_ts: datetime | None = None
    language: str = "en"
    image_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)  # symbols/issuers referenced
    issuer_ids: list[str] = Field(default_factory=list)
    instrument_vt_symbols: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None


class CompanyNews(NewsItem):
    """News with a primary issuer / symbol binding."""

    symbol: str | None = None
    issuer_id: str | None = None


class WorldNews(NewsItem):
    """General-market / macro / geopolitical news."""

    region: str | None = None
    country: str | None = None
    event_type: str | None = None  # macro | geopolitical | market | sector
