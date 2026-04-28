"""Index XBRL standardised financials + ratios at L2 ``standardized_financials`` and ``ratios``."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def _render_statement(row) -> str:
    line_items = getattr(row, "line_items", None) or {}
    items_str = ", ".join(f"{k}={v}" for k, v in list(line_items.items())[:24])
    return (
        f"Financial statement for {getattr(row, 'instrument_id', '?')} "
        f"period={getattr(row, 'fiscal_period', '?')} "
        f"end={getattr(row, 'period_end', '?')}. {items_str}"
    )


def index_sec_xbrl(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_fundamentals import FinancialStatement
    except Exception:  # pragma: no cover
        logger.info("FinancialStatement ORM unavailable; skipping XBRL index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(FinancialStatement).order_by(
                FinancialStatement.period_end.desc()
            )
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = _render_statement(row)
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"xbrl:{row.id}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "period_end", "") or ""),
                            "source_id": str(row.id),
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read XBRL statements.")
        return 0
    return rag.index_chunks("sec_xbrl", items, level="l2")


def index_financial_ratios(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_fundamentals import FinancialRatios
    except Exception:  # pragma: no cover
        logger.info("FinancialRatios ORM unavailable; skipping ratios index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(FinancialRatios).order_by(FinancialRatios.period_end.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                ratios = {
                    k: getattr(row, k, None)
                    for k in (
                        "pe_ratio",
                        "pb_ratio",
                        "ps_ratio",
                        "ev_to_ebitda",
                        "current_ratio",
                        "debt_to_equity",
                        "roa",
                        "roe",
                        "gross_margin",
                        "operating_margin",
                        "net_margin",
                    )
                    if getattr(row, k, None) is not None
                }
                if not ratios:
                    continue
                items_str = ", ".join(f"{k}={v}" for k, v in ratios.items())
                text = (
                    f"Ratios for {getattr(row, 'vt_symbol', '?')} "
                    f"as of {getattr(row, 'period_end', '?')}: {items_str}."
                )
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"ratio:{row.id}",
                            "vt_symbol": str(getattr(row, "vt_symbol", "") or ""),
                            "as_of": str(getattr(row, "period_end", "") or ""),
                            "source_id": str(row.id),
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read financial ratios.")
        return 0
    return rag.index_chunks("financial_ratios", items, level="l2")


__all__ = ["index_financial_ratios", "index_sec_xbrl"]
