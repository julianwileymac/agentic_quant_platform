"""Index CFPB consumer complaints at L3 ``cfpb_complaint``."""
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
    for key in ("vt_symbol", "ticker", "cusip", "cik"):
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
        payloads.append(
            {
                "document_id": str(meta.get("source_id") or meta.get("doc_id") or ""),
                "content_text": chunk.text,
                "instrument_urn": _instrument_urn_from_metadata(meta),
                "valid_from": meta.get("as_of"),
                "glossary_terms": extract_glossary_terms(chunk.text),
            }
        )
    try:
        emitted = emit_documents_batch(payloads)
        logger.info("Emitted %d CFPB Document aspects.", len(emitted))
    except Exception:
        logger.exception(
            "Document-aspect emission failed for cfpb_complaints; continuing index run."
        )


def index_cfpb_complaints(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 20000,
    company: str | None = None,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import CfpbComplaint
    except Exception:  # pragma: no cover
        logger.info("CfpbComplaint ORM unavailable; skipping CFPB index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(CfpbComplaint).order_by(CfpbComplaint.date_received.desc())
            if company:
                q = q.filter(CfpbComplaint.company == company)
            if limit:
                q = q.limit(limit)
            for row in q.all():
                narrative = (getattr(row, "consumer_complaint_narrative", "") or "").strip()
                product = getattr(row, "product", "") or ""
                issue = getattr(row, "issue", "") or ""
                head = (
                    f"CFPB complaint {row.complaint_id} against {row.company}. "
                    f"Product={product}. Issue={issue}. State={getattr(row, 'state', '')}. "
                    f"Date={getattr(row, 'date_received', '')}."
                )
                items.append(
                    (
                        Chunk(text=head, index=0, token_count=len(head.split())),
                        {
                            "doc_id": f"cfpb:{row.complaint_id}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "date_received", "") or ""),
                            "source_id": str(row.complaint_id),
                            "company": row.company,
                            "product": product,
                            "issue": issue,
                        },
                    )
                )
                if narrative:
                    for ch in semantic_chunks(narrative, max_tokens=384, heading=issue):
                        items.append(
                            (
                                ch,
                                {
                                    "doc_id": f"cfpb:{row.complaint_id}#c{ch.index}",
                                    "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                                    "as_of": str(getattr(row, "date_received", "") or ""),
                                    "source_id": str(row.complaint_id),
                                    "company": row.company,
                                    "product": product,
                                    "issue": issue,
                                },
                            )
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read CFPB complaints.")
        return 0
    _emit_document_aspects(items)
    return rag.index_chunks("cfpb_complaints", items, level="l3")


__all__ = ["index_cfpb_complaints"]
