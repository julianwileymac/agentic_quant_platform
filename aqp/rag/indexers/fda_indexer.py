"""Index FDA applications, adverse events, and recalls at L3."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def index_fda_applications(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 10000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import FdaApplication
    except Exception:  # pragma: no cover
        logger.info("FdaApplication ORM unavailable; skipping FDA application index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(FdaApplication).order_by(FdaApplication.submission_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = (
                    f"FDA application {row.application_number} by {row.sponsor_name}. "
                    f"Type={getattr(row, 'application_type', '')}. "
                    f"Submission={getattr(row, 'submission_date', '')}. "
                    f"Status={getattr(row, 'submission_status', '')}. "
                    f"Drug={getattr(row, 'drug_name', '')}. "
                    f"Indication={getattr(row, 'indication', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"fda_app:{row.application_number}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "submission_date", "") or ""),
                            "source_id": str(row.application_number),
                            "sponsor": row.sponsor_name,
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read FDA applications.")
        return 0
    return rag.index_chunks("fda_applications", items, level="l3")


def index_fda_adverse_events(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 20000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import FdaAdverseEvent
    except Exception:  # pragma: no cover
        logger.info("FdaAdverseEvent ORM unavailable; skipping FDA AE index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(FdaAdverseEvent).order_by(FdaAdverseEvent.received_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = (
                    f"FDA adverse event {row.report_id} for {getattr(row, 'product_name', '')}. "
                    f"Outcomes={getattr(row, 'outcomes', '')}. "
                    f"Reactions={getattr(row, 'reactions', '')}. "
                    f"Received={getattr(row, 'received_date', '')}. "
                    f"Manufacturer={getattr(row, 'manufacturer_name', '')}. "
                    f"Serious={getattr(row, 'is_serious', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"fda_ae:{row.report_id}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "received_date", "") or ""),
                            "source_id": str(row.report_id),
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read FDA adverse events.")
        return 0
    return rag.index_chunks("fda_adverse_events", items, level="l3")


def index_fda_recalls(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_regulatory import FdaRecall
    except Exception:  # pragma: no cover
        logger.info("FdaRecall ORM unavailable; skipping recalls index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(FdaRecall).order_by(FdaRecall.recall_initiation_date.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = (
                    f"FDA recall {row.recall_number} by {row.recalling_firm}. "
                    f"Class={getattr(row, 'classification', '')}. "
                    f"Product={getattr(row, 'product_description', '')}. "
                    f"Reason={getattr(row, 'reason_for_recall', '')}. "
                    f"Initiated={getattr(row, 'recall_initiation_date', '')}. "
                    f"Status={getattr(row, 'status', '')}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"fda_recall:{row.recall_number}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "recall_initiation_date", "") or ""),
                            "source_id": str(row.recall_number),
                            "classification": getattr(row, "classification", ""),
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read FDA recalls.")
        return 0
    return rag.index_chunks("fda_recalls", items, level="l3")


__all__ = [
    "index_fda_adverse_events",
    "index_fda_applications",
    "index_fda_recalls",
]
