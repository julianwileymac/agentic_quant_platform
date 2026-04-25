"""News ingestion + storage for the trader crew.

Surface:

- :class:`INewsProvider` — async/sync fetch interface.
- :class:`YFinanceNewsProvider` — default adapter using ``yf.Ticker.news``.
- :class:`NewsStore` — lightweight DuckDB-backed store for batch ingest
  + sentiment enrichment.
- :func:`get_news_provider` — factory that honours ``settings.news_provider``.
"""
from __future__ import annotations

from aqp.data.news.base import INewsProvider, NewsItem
from aqp.data.news.store import NewsStore
from aqp.data.news.yfinance_news import YFinanceNewsProvider


def get_news_provider(slug: str | None = None) -> INewsProvider | None:
    """Return the news provider configured for the platform.

    ``slug`` overrides :data:`aqp.config.settings.news_provider`. Returns
    ``None`` when the slug is ``"none"`` so callers can short-circuit
    cheaply.
    """
    from aqp.config import settings

    active = (slug or settings.news_provider or "yfinance").lower()
    if active in ("", "none", "off"):
        return None
    if active == "yfinance":
        return YFinanceNewsProvider()
    raise ValueError(f"unknown news provider: {active!r}")


__all__ = [
    "INewsProvider",
    "NewsItem",
    "NewsStore",
    "YFinanceNewsProvider",
    "get_news_provider",
]
