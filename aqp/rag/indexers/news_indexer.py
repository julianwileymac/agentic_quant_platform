"""Index news + sentiment items at L2 ``news_articles``."""
from __future__ import annotations

import logging
import re
from typing import Any

from aqp.metadata import make_urn
from aqp.rag.chunker import Chunk, semantic_chunks
from aqp.rag.document_aspects import (
    DocumentEmissionPayload,
    emit_documents_batch,
    extract_glossary_terms,
)
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)
_INSTRUMENT_ID_SANITIZER = re.compile(r"[^A-Za-z0-9._:-]+")


def _instrument_urn_from_metadata(meta: dict[str, Any]) -> str | None:
    for key in ("ticker", "vt_symbol", "cusip", "cik"):
        raw_value = str(meta.get(key) or "").strip()
        if not raw_value:
            continue
        urn_id = _INSTRUMENT_ID_SANITIZER.sub("-", raw_value).strip("-.:")
        if urn_id:
            return make_urn("instrument", "prod", urn_id)
    return None


def _emit_document_aspects(items: list[tuple[Chunk, dict[str, Any]]]) -> None:
    if not items:
        return
    payloads: list[DocumentEmissionPayload] = []
    for chunk, meta in items:
        source_url = str(meta.get("source_url") or "").strip() or None
        if source_url is None:
            source_id = str(meta.get("source_id") or "").strip()
            if source_id.startswith(("http://", "https://")):
                source_url = source_id
        payloads.append(
            {
                "document_id": str(meta.get("source_id") or meta.get("doc_id") or ""),
                "content_text": chunk.text,
                "instrument_urn": _instrument_urn_from_metadata(meta),
                "valid_from": meta.get("as_of"),
                "glossary_terms": extract_glossary_terms(chunk.text),
                "source_url": source_url,
            }
        )
    try:
        emitted = emit_documents_batch(payloads)
        logger.info("Emitted %d news Document aspects.", len(emitted))
    except Exception:
        logger.exception(
            "Document-aspect emission failed for news_sentiment; continuing index run."
        )


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
                            "source_url": str(getattr(row, "url", "") or ""),
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
                                    "source_url": str(getattr(row, "url", "") or ""),
                                    "title": title,
                                    "source": getattr(row, "source", "") or "",
                                },
                            )
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read news rows.")
        return 0
    _emit_document_aspects(items)
    return rag.index_chunks("news_sentiment", items, level="l2")


__all__ = ["index_news_sentiment"]
