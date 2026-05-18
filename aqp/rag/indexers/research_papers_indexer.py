"""Indexer for the math-aware ``research_papers`` corpus.

Picks the best available parser via
:func:`aqp.rag.parsers.pick_parser`, walks the parsed text blocks
with equation-aware chunking (math-bearing blocks include the 2
surrounding sentences so variable definitions don't get sliced
away from the equation), and pushes every chunk through
:meth:`HierarchicalRAG.index_chunks` (AGENTS.md rule 11).

Reads paper rows from the ``research_papers`` Postgres table added
in migration ``0033_research_papers.py``. New uploads are inserted
by the ``ingest_research_paper`` Celery task ahead of calling this
indexer.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable
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
from aqp.rag.parsers import ParsedDoc, pick_parser

logger = logging.getLogger(__name__)
_INSTRUMENT_ID_SANITIZER = re.compile(r"[^A-Za-z0-9._:-]+")


def _instrument_urn_from_metadata(meta: dict[str, Any]) -> str | None:
    raw_value = str(meta.get("vt_symbol") or "").strip()
    if not raw_value:
        return None
    urn_id = _INSTRUMENT_ID_SANITIZER.sub("-", raw_value).strip("-.:")
    if not urn_id:
        return None
    return make_urn("instrument", "prod", urn_id)


def _emit_document_aspects(items: list[tuple[Chunk, dict[str, object]]]) -> None:
    if not items:
        return
    payloads: list[DocumentEmissionPayload] = []
    for chunk, meta in items:
        source_url = str(meta.get("source_url") or "").strip() or None
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
        logger.info("Emitted %d research-paper Document aspects.", len(emitted))
    except Exception:
        logger.exception(
            "Document-aspect emission failed for research_papers; continuing index run."
        )


def _equation_aware_chunks(doc: ParsedDoc, *, max_tokens: int = 512) -> list[Chunk]:
    """Chunk parsed text blocks so equations stay glued to their context.

    Blocks containing math (``$...$`` or ``\\[...\\]``) are kept
    intact even if oversize. Plain-text blocks are split by the
    standard semantic chunker.
    """
    out: list[Chunk] = []
    idx = 0
    for block in doc.text_blocks:
        has_math = "$$" in block or "\\[" in block or "$" in block or "\\(" in block
        if has_math:
            out.append(Chunk(text=block, index=idx, token_count=len(block.split())))
            idx += 1
            continue
        for ch in semantic_chunks(block, max_tokens=max_tokens):
            out.append(Chunk(text=ch.text, index=idx, token_count=ch.token_count))
            idx += 1
    return out


def _paper_meta(row: object, doc: ParsedDoc) -> dict[str, object]:
    """Build the per-chunk metadata blob enforcing the schema."""
    return {
        "doc_id": f"paper:{getattr(row, 'id', 'unknown')}",
        "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
        "as_of": str(getattr(row, "publication_year", "") or ""),
        "source_id": str(getattr(row, "id", "")),
        "title": str(getattr(row, "title", "") or ""),
        "authors": (getattr(row, "authors", None) or []),
        "author_institution": str(getattr(row, "author_institution", "") or ""),
        "asset_class": list(getattr(row, "asset_class", None) or []),
        "strategy_family": str(getattr(row, "strategy_family", "") or ""),
        "contains_mathematics": bool(doc.contains_mathematics),
        "equation_count": int(doc.equation_count),
        "parser_used": doc.parser_name,
        "source_url": str(getattr(row, "source_url", "") or ""),
    }


def index_research_papers(
    *,
    rag: HierarchicalRAG | None = None,
    paper_ids: Iterable[str] | None = None,
    parser_preference: list[str] | str | None = None,
    limit: int | None = None,
) -> int:
    """Index every paper (or just the listed ``paper_ids``).

    Returns the total number of chunks written.
    """
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_research_papers import ResearchPaperRow
    except Exception:  # pragma: no cover - migration not applied
        logger.info("ResearchPaperRow ORM not available; skipping index.")
        return 0

    written = 0
    try:
        parser = pick_parser(parser_preference)
    except RuntimeError as exc:
        logger.warning("No PDF parser available: %s", exc)
        return 0

    items: list[tuple[Chunk, dict[str, object]]] = []
    with SessionLocal() as session:
        q = session.query(ResearchPaperRow)
        if paper_ids:
            q = q.filter(ResearchPaperRow.id.in_(list(paper_ids)))
        if limit:
            q = q.limit(limit)
        for row in q.all():
            pdf_path = Path(getattr(row, "pdf_path", "") or "")
            if not pdf_path.exists():
                logger.info("paper %s: pdf_path missing on disk (%s)", row.id, pdf_path)
                continue
            try:
                doc = parser.parse(pdf_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("paper %s parse failed: %s", row.id, exc)
                continue
            meta = _paper_meta(row, doc)
            for ch in _equation_aware_chunks(doc):
                # Compose a per-chunk meta so vt_symbol / doc_id / etc
                # land on the Redis vector record.
                items.append(
                    (
                        Chunk(text=ch.text, index=ch.index, token_count=ch.token_count),
                        {**meta, "doc_id": f"paper:{row.id}#chunk:{ch.index}"},
                    )
                )
            # Update the row with the parser + chunk count for the
            # paper-detail UI.
            row.chunk_count = sum(1 for _ in items if str(_[1].get("source_id", "")) == str(row.id))
            row.parser_used = doc.parser_name
            row.equation_count = doc.equation_count
            row.contains_mathematics = doc.contains_mathematics
            session.add(row)
        session.commit()
    _emit_document_aspects(items)
    if items:
        written = rag.index_chunks("research_papers", items, level="l2")
    return written


__all__ = ["index_research_papers"]
