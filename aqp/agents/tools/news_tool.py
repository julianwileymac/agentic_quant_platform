"""News + sentiment tool for the trader crew.

Pulls recent headlines from :mod:`aqp.data.news` (yfinance adapter by
default), optionally scores each with the configured sentiment model
from :mod:`aqp.ml.applications.sentiment`, and returns a compact
transcript the NEWS / SENTIMENT analyst roles can reason over.

Gracefully handles the case where the sentiment model isn't available
so the crew can still operate on raw headlines.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NewsInput(BaseModel):
    vt_symbol: str = Field(..., description="Canonical vt_symbol (e.g. AAPL.NASDAQ)")
    as_of: str | None = Field(default=None, description="ISO date; defaults to today UTC")
    lookback_days: int = Field(default=7, description="Trailing window for headlines")
    include_sentiment: bool = Field(default=True, description="Score each item with the sentiment model")
    max_items: int = Field(default=15, ge=1, le=100)


def fetch_news_items(
    vt_symbol: str,
    as_of: datetime | str | None = None,
    lookback_days: int = 7,
    max_items: int = 15,
) -> list[dict[str, object]]:
    """Return raw headline dicts from the configured news provider."""
    try:
        from aqp.data.news import get_news_provider
    except Exception as exc:  # pragma: no cover - defensive import
        logger.warning("news subsystem unavailable: %s", exc)
        return []

    provider = get_news_provider()
    if provider is None:
        return []

    if as_of is None:
        as_of_dt = datetime.utcnow()
    elif isinstance(as_of, str):
        as_of_dt = datetime.fromisoformat(as_of)
    else:
        as_of_dt = as_of
    since = as_of_dt - timedelta(days=lookback_days)

    try:
        return provider.fetch(vt_symbol, since=since, until=as_of_dt, limit=max_items)
    except Exception as exc:
        logger.warning("news provider fetch failed for %s: %s", vt_symbol, exc)
        return []


def score_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Attach a ``sentiment`` float in [-1, 1] to each item when possible."""
    if not items:
        return items
    try:
        from aqp.ml.applications.sentiment import get_scorer

        scorer = get_scorer()
    except Exception as exc:
        logger.info("sentiment scoring skipped: %s", exc)
        return items

    texts = [str(it.get("title") or it.get("headline") or "") for it in items]
    try:
        scores = scorer.score(texts)
    except Exception as exc:
        logger.info("sentiment scoring failed: %s", exc)
        return items

    for item, score in zip(items, scores, strict=False):
        item["sentiment"] = round(float(score), 4)
    return items


def _format_items(items: list[dict[str, object]]) -> str:
    if not items:
        return "news: no recent items"
    lines = ["id,date,title,source,sentiment"]
    for i, item in enumerate(items):
        date = item.get("published_at") or item.get("date") or ""
        title = str(item.get("title") or item.get("headline") or "").replace(",", " ")
        src = str(item.get("source") or item.get("publisher") or "").replace(",", " ")
        sent = item.get("sentiment", "")
        lines.append(f"{i},{date},{title},{src},{sent}")
    return "\n".join(lines)


class NewsTool(BaseTool):
    name: str = "news_digest"
    description: str = (
        "Return a dated digest of recent headlines (and sentiment scores when "
        "the FinGPT / FinBERT sentiment model is installed) for a ticker. "
        "Use this from the NEWS or SENTIMENT analyst roles."
    )
    args_schema: type[BaseModel] = NewsInput

    def _run(  # type: ignore[override]
        self,
        vt_symbol: str,
        as_of: str | None = None,
        lookback_days: int = 7,
        include_sentiment: bool = True,
        max_items: int = 15,
    ) -> str:
        items = fetch_news_items(vt_symbol, as_of, lookback_days, max_items)
        if include_sentiment and items:
            items = score_items(items)
        return _format_items(items)
