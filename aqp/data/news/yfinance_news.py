"""yfinance news adapter.

Uses ``yf.Ticker.news`` which is free but rate-limited. Normalizes the
payload shape across yfinance versions (older releases use ``providerPublishTime``
while newer ones use ``content.pubDate``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aqp.data.news.base import INewsProvider

logger = logging.getLogger(__name__)


def _ticker_root(vt_symbol: str) -> str:
    return vt_symbol.split(".", 1)[0]


def _coerce_ts(raw) -> str:
    """Return an ISO timestamp string from whatever yfinance gives us."""
    if raw is None:
        return ""
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc).isoformat()
        except Exception:
            return ""
    if isinstance(raw, datetime):
        return raw.isoformat()
    return str(raw)


class YFinanceNewsProvider(INewsProvider):
    name = "yfinance"

    def fetch(
        self,
        vt_symbol: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 25,
    ) -> list[dict]:
        try:
            import yfinance as yf
        except ImportError:  # pragma: no cover
            logger.warning("yfinance is not installed; news fetch returning empty list")
            return []

        try:
            ticker = yf.Ticker(_ticker_root(vt_symbol))
            raw_items = list(getattr(ticker, "news", []) or [])
        except Exception as exc:
            logger.info("yfinance news fetch failed for %s: %s", vt_symbol, exc)
            return []

        items: list[dict] = []
        for idx, item in enumerate(raw_items[: limit * 3]):
            # yfinance >=0.2.45 nests the payload under `content`.
            content = item.get("content") if isinstance(item, dict) else None
            title = (
                (content or {}).get("title")
                or item.get("title")
                or item.get("headline")
                or ""
            )
            if not title:
                continue
            source = (
                (content or {}).get("provider", {}).get("displayName")
                if isinstance((content or {}).get("provider"), dict)
                else None
            ) or item.get("publisher") or item.get("source") or ""
            url = (
                (content or {}).get("canonicalUrl", {}).get("url")
                if isinstance((content or {}).get("canonicalUrl"), dict)
                else None
            ) or item.get("link") or ""
            ts = (
                (content or {}).get("pubDate")
                or item.get("providerPublishTime")
                or item.get("publishedAt")
                or item.get("published_at")
            )
            normalized = {
                "id": item.get("uuid") or item.get("id") or f"yf-{idx}",
                "title": str(title),
                "source": str(source),
                "url": str(url),
                "published_at": _coerce_ts(ts),
                "summary": str((content or {}).get("summary", "") or ""),
            }
            # Apply since/until filters if provided (best effort).
            if since or until:
                try:
                    iso = normalized["published_at"]
                    if iso:
                        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                        if since and dt < since:
                            continue
                        if until and dt > until:
                            continue
                except Exception:
                    pass
            items.append(normalized)
            if len(items) >= limit:
                break
        return items
