"""Abstract news provider contract.

Each concrete adapter returns a list of dicts with **at least** the
``title``, ``published_at`` and ``source`` keys so downstream consumers
(sentiment processor, trader-crew analysts, UI) can rely on a stable
shape regardless of the backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsItem:
    """Minimal structured item — provided for type-aware callers."""

    id: str
    title: str
    source: str
    url: str = ""
    published_at: datetime | None = None
    summary: str = ""
    sentiment: float | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else "",
            "summary": self.summary,
            "sentiment": self.sentiment,
        }


class INewsProvider(ABC):
    """Sync news provider (pairs with FastAPI + Celery worker)."""

    name: str = "news"

    @abstractmethod
    def fetch(
        self,
        vt_symbol: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 25,
    ) -> list[dict]:
        """Return a list of normalized news dicts."""
