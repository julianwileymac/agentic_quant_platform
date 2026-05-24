"""Ingest AV news sentiment articles into the Redis-OM AVNewsArticle index.

Good companion to ``pipelines/examples/ingest_minio_json_to_redis.py`` for
building a RAG-ready AV news corpus.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Iterable

from alphavantage_client import AlphaVantageClient

from pipelines.alphavantage_om import AVNewsArticle, ensure_av_migrated


def ingest_news(tickers: Iterable[str]) -> int:
    client = AlphaVantageClient()
    try:
        ensure_av_migrated()
        payload = client.intelligence.news(tickers=list(tickers), limit=200)
    finally:
        client.close()

    count = 0
    for article in payload.feed:
        article_url = article.url or ""
        if not article_url:
            continue
        article_id = hashlib.sha256(article_url.encode("utf-8")).hexdigest()
        try:
            record = AVNewsArticle(
                article_id=article_id,
                url=article_url,
                title=article.title or "",
                summary=article.summary or "",
                source=article.source or "",
                source_domain=article.source_domain or "",
                time_published=article.time_published or "",
                tickers=[t.ticker for t in (article.ticker_sentiment or []) if t.ticker],
                topics=[t.topic for t in (article.topics or []) if t.topic],
                overall_sentiment_score=float(article.overall_sentiment_score or 0.0),
                overall_sentiment_label=article.overall_sentiment_label or "",
                created_at=time.time(),
                raw=article.model_dump(by_alias=False),
            )
            record.save()
            count += 1
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("redis-om save failed for %s", article_id)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    inserted = ingest_news(["AAPL", "MSFT", "GOOGL"])
    print(f"ingested {inserted} AV news articles into Redis")
