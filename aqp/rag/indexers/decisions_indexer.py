"""Index past ``agent_decisions`` rows as the L0 alpha base.

Mirrors paper RAG#0: the LLM agent learns the characteristics of
previously successful (or unsuccessful) decisions before generating new
ideas.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from aqp.metadata import make_urn
from aqp.rag.chunker import Chunk
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
        logger.info("Emitted %d decision Document aspects.", len(emitted))
    except Exception:
        logger.exception(
            "Document-aspect emission failed for decisions; continuing index run."
        )


def render_decision_text(payload: dict[str, Any]) -> str:
    """Render an ``AgentDecision`` payload into one indexable paragraph."""
    sym = payload.get("vt_symbol") or payload.get("symbol") or "?"
    asof = payload.get("as_of") or payload.get("timestamp") or ""
    pm = (payload.get("portfolio") or payload.get("portfolio_decision") or {}) or {}
    action = pm.get("action") or payload.get("action") or "hold"
    rationale = (
        pm.get("rationale")
        or payload.get("rationale")
        or payload.get("summary")
        or ""
    )
    plan = payload.get("plan") or {}
    risk = payload.get("verdict") or payload.get("risk") or {}
    outcome = payload.get("outcome") or payload.get("realized_pnl")
    parts = [
        f"Symbol={sym} as_of={asof} action={action}.",
        f"Rationale: {rationale.strip()[:1200]}" if rationale else "",
        f"Plan: {plan!r}" if plan else "",
        f"Risk: {risk!r}" if risk else "",
    ]
    if outcome is not None:
        parts.append(f"Outcome: {outcome}")
    return "\n".join(p for p in parts if p)


def index_decisions(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
    since_days: int | None = 365,
) -> int:
    """Walk ``agent_decisions`` and index them at L0."""
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import AgentDecision  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        logger.info("AgentDecision ORM not available; skipping decisions index.")
        return 0
    cutoff = (
        datetime.utcnow() - timedelta(days=since_days) if since_days else None
    )
    items: list[tuple[Chunk, dict[str, Any]]] = []
    try:
        with SessionLocal() as session:
            query = session.query(AgentDecision)
            if cutoff is not None and hasattr(AgentDecision, "as_of"):
                query = query.filter(AgentDecision.as_of >= cutoff)
            if limit:
                query = query.limit(limit)
            for row in query.all():
                payload: dict[str, Any] = {}
                for col in (
                    "id",
                    "vt_symbol",
                    "as_of",
                    "action",
                    "rationale",
                    "summary",
                    "plan",
                    "portfolio",
                    "portfolio_decision",
                    "verdict",
                    "outcome",
                    "realized_pnl",
                ):
                    if hasattr(row, col):
                        payload[col] = getattr(row, col)
                if not payload:
                    continue
                text = render_decision_text(payload)
                if not text:
                    continue
                meta = {
                    "doc_id": str(payload.get("id") or row.id),
                    "vt_symbol": str(payload.get("vt_symbol", "") or ""),
                    "as_of": str(payload.get("as_of") or ""),
                    "source_id": str(payload.get("id") or ""),
                    "action": payload.get("action") or "",
                }
                items.append((Chunk(text=text, index=0, token_count=len(text.split())), meta))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read agent decisions.")
        return 0
    _emit_document_aspects(items)
    return rag.index_chunks("decisions", items, level="l0")


def index_decision_payloads(
    payloads: Iterable[dict[str, Any]],
    *,
    rag: HierarchicalRAG | None = None,
) -> int:
    """Index a stream of in-memory decision payloads (used by the reflector)."""
    rag = rag or get_default_rag()
    items: list[tuple[Chunk, dict[str, Any]]] = []
    for p in payloads:
        text = render_decision_text(p)
        if not text:
            continue
        meta = {
            "doc_id": str(p.get("id") or ""),
            "vt_symbol": str(p.get("vt_symbol", "") or ""),
            "as_of": str(p.get("as_of") or ""),
            "source_id": str(p.get("id") or ""),
        }
        items.append((Chunk(text=text, index=0, token_count=len(text.split())), meta))
    _emit_document_aspects(items)
    return rag.index_chunks("decisions", items, level="l0")


__all__ = [
    "index_decision_payloads",
    "index_decisions",
    "render_decision_text",
]
