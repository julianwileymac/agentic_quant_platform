"""Index SEC EDGAR filings index at L2 ``disclosures``."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk, semantic_chunks
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def index_sec_filings(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import SecFiling
    except Exception:  # pragma: no cover
        logger.info("SecFiling ORM not available; skipping SEC index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(SecFiling).order_by(SecFiling.filed_at.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                # Render a one-paragraph card per filing; full body indexing
                # is left to a separate body-extractor task.
                text = (
                    f"SEC filing for CIK={row.cik} ({getattr(row, 'ticker', '?')}). "
                    f"Form={row.form_type}. Filed={getattr(row, 'filed_at', '')}. "
                    f"Period={getattr(row, 'period_of_report', '')}. "
                    f"URL={getattr(row, 'primary_doc_url', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"sec:{row.id}",
                            "vt_symbol": str(getattr(row, "ticker", "") or ""),
                            "as_of": str(getattr(row, "filed_at", "") or ""),
                            "source_id": str(getattr(row, "accession_number", row.id)),
                            "form_type": getattr(row, "form_type", "") or "",
                        },
                    )
                )
                # Optional: semantic chunks of the abstract/summary if present
                summary = (getattr(row, "summary", "") or "").strip()
                if summary:
                    for ch in semantic_chunks(summary, max_tokens=384, heading=row.form_type or ""):
                        items.append(
                            (
                                ch,
                                {
                                    "doc_id": f"sec:{row.id}#sum:{ch.index}",
                                    "vt_symbol": str(getattr(row, "ticker", "") or ""),
                                    "as_of": str(getattr(row, "filed_at", "") or ""),
                                    "source_id": str(getattr(row, "accession_number", row.id)),
                                    "form_type": getattr(row, "form_type", "") or "",
                                },
                            )
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read SEC filings.")
        return 0
    return rag.index_chunks("sec_filings", items, level="l2")


__all__ = ["index_sec_filings"]
