"""Index USPTO patents, trademarks, and assignments at L3."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk, semantic_chunks
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def index_uspto_patents(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 10000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import UsptoPatent
    except Exception:  # pragma: no cover
        logger.info("UsptoPatent ORM unavailable; skipping patents index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(UsptoPatent).order_by(UsptoPatent.grant_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                title = getattr(row, "title", "") or ""
                abstract = getattr(row, "abstract", "") or ""
                head = (
                    f"USPTO patent {row.patent_number} granted to {row.assignee}. "
                    f"Title='{title}'. Granted={getattr(row, 'grant_date', '')}. "
                    f"Filed={getattr(row, 'filing_date', '')}. "
                    f"Class={getattr(row, 'classification', '')}."
                )
                items.append(
                    (
                        Chunk(text=head, index=0, token_count=len(head.split())),
                        {
                            "doc_id": f"patent:{row.patent_number}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "grant_date", "") or ""),
                            "source_id": str(row.patent_number),
                            "assignee": row.assignee,
                            "title": title,
                        },
                    )
                )
                if abstract:
                    for ch in semantic_chunks(abstract, max_tokens=384, heading=title):
                        items.append(
                            (
                                ch,
                                {
                                    "doc_id": f"patent:{row.patent_number}#a{ch.index}",
                                    "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                                    "as_of": str(getattr(row, "grant_date", "") or ""),
                                    "source_id": str(row.patent_number),
                                    "assignee": row.assignee,
                                    "title": title,
                                },
                            )
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read USPTO patents.")
        return 0
    return rag.index_chunks("uspto_patents", items, level="l3")


def index_uspto_trademarks(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 10000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import UsptoTrademark
    except Exception:  # pragma: no cover
        logger.info("UsptoTrademark ORM unavailable; skipping trademarks index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(UsptoTrademark).order_by(UsptoTrademark.filing_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = (
                    f"USPTO trademark {row.serial_number} '{getattr(row, 'mark_text', '')}' "
                    f"by {row.owner}. Status={getattr(row, 'status', '')}. "
                    f"Class={getattr(row, 'class_codes', '')}. "
                    f"Filed={getattr(row, 'filing_date', '')}. "
                    f"Registered={getattr(row, 'registration_date', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"trademark:{row.serial_number}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "filing_date", "") or ""),
                            "source_id": str(row.serial_number),
                            "owner": row.owner,
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read USPTO trademarks.")
        return 0
    return rag.index_chunks("uspto_trademarks", items, level="l3")


def index_uspto_assignments(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import UsptoAssignment
    except Exception:  # pragma: no cover
        logger.info("UsptoAssignment ORM unavailable; skipping assignments index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(UsptoAssignment).order_by(UsptoAssignment.recorded_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = (
                    f"USPTO patent assignment from {row.assignor} to {row.assignee} "
                    f"recorded={getattr(row, 'recorded_date', '')}. "
                    f"Patents={getattr(row, 'patents', '')}. "
                    f"Conveyance={getattr(row, 'conveyance_text', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"assignment:{row.assignment_id}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "recorded_date", "") or ""),
                            "source_id": str(row.assignment_id),
                            "assignor": row.assignor,
                            "assignee": row.assignee,
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read USPTO assignments.")
        return 0
    return rag.index_chunks("uspto_assignments", items, level="l3")


__all__ = [
    "index_uspto_assignments",
    "index_uspto_patents",
    "index_uspto_trademarks",
]
