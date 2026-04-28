"""Index news + sentiment items at L2 ``news_articles``."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk, semantic_chunks
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def index_news_sentiment(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 10000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_news import NewsItemRow
    except Exception:  # pragma: no cover
        logger.info("NewsItemRow ORM unavailable; skipping news index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(NewsItemRow).order_by(NewsItemRow.published_at.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                title = (getattr(row, "title", "") or "").strip()
                summary = (getattr(row, "summary", "") or getattr(row, "body", "") or "").strip()
                if not (title or summary):
                    continue
                head = f"{title}. {summary}"[:8000]
                # One overview chunk plus semantic chunks of the body.
                items.append(
                    (
                        Chunk(text=head, index=0, token_count=len(head.split())),
                        {
                            "doc_id": f"news:{row.id}",
                            "vt_symbol": "",
                            "as_of": str(getattr(row, "published_at", "") or ""),
                            "source_id": str(getattr(row, "url", row.id)),
                            "title": title,
                            "source": getattr(row, "source", "") or "",
                        },
                    )
                )
                if summary:
                    for ch in semantic_chunks(summary, max_tokens=384, heading=title):
                        items.append(
                            (
                                ch,
                                {
                                    "doc_id": f"news:{row.id}#c{ch.index}",
                                    "vt_symbol": "",
                                    "as_of": str(getattr(row, "published_at", "") or ""),
                                    "source_id": str(getattr(row, "url", row.id)),
                                    "title": title,
                                    "source": getattr(row, "source", "") or "",
                                },
                            )
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read news rows.")
        return 0
    return rag.index_chunks("news_sentiment", items, level="l2")


__all__ = ["index_news_sentiment"]
