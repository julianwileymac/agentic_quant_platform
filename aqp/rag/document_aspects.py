"""Bridge between RAG indexers and the EntityAspect store.

Every chunk an indexer produces is wrapped in a Document Pydantic model
and persisted via write_aspect() BEFORE HierarchicalRAG.index_chunks
embeds it. This lets agents query 'all Documents tagged with the
glossary term Volatility that have lineage to a given dataset URN'.
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, NotRequired, Required, TypedDict

from aqp.metadata import ImmutableAspectError, make_urn, write_aspect
from aqp.metadata.openmetadata.models_glossary import Document
from aqp.metadata.writer import AspectWriterControl
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

_MAX_CONTENT_TEXT_CHARS = 4096
_ID_SANITIZER = re.compile(r"[^A-Za-z0-9._:-]+")

_DEFAULT_FINANCIAL_TERMS: tuple[str, ...] = (
    "Volatility",
    "Sharpe Ratio",
    "Drawdown",
    "Beta",
    "Alpha",
    "Correlation",
    "Cointegration",
    "Mean Reversion",
    "Momentum",
    "Carry",
    "Skewness",
    "Kurtosis",
    "Bid-Ask Spread",
    "Liquidity",
    "Risk Premium",
    "Implied Volatility",
    "Realized Volatility",
    "Yield Curve",
    "Duration",
    "Convexity",
    "Greeks",
    "Delta",
    "Gamma",
    "Theta",
    "Vega",
    "Rho",
    "Earnings Surprise",
    "Free Cash Flow",
    "Return on Equity",
    "Debt to Equity",
    "Price to Earnings",
    "Tobin's Q",
    "EBITDA",
    "Operating Margin",
    "Gross Margin",
)


def _resolve_financial_terms() -> tuple[str, ...]:
    try:
        from aqp.rag.parsers import _FINANCIAL_TERMS  # type: ignore[attr-defined]
    except Exception:
        return _DEFAULT_FINANCIAL_TERMS
    if isinstance(_FINANCIAL_TERMS, tuple) and all(
        isinstance(term, str) and term.strip() for term in _FINANCIAL_TERMS
    ):
        return _FINANCIAL_TERMS
    if isinstance(_FINANCIAL_TERMS, list) and all(
        isinstance(term, str) and term.strip() for term in _FINANCIAL_TERMS
    ):
        return tuple(_FINANCIAL_TERMS)
    return _DEFAULT_FINANCIAL_TERMS


_FINANCIAL_TERMS = _resolve_financial_terms()
_FINANCIAL_TERM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        term,
        re.compile(
            rf"(?<!\w){re.escape(term).replace(r'\ ', r'\s+').replace(r'\-', r'[-\s]')}(?!\w)",
            re.IGNORECASE,
        ),
    )
    for term in _FINANCIAL_TERMS
)


class DocumentEmissionPayload(TypedDict):
    """Payload accepted by :func:`emit_documents_batch`."""

    document_id: Required[str]
    content_text: Required[str]
    instrument_urn: NotRequired[str | None]
    valid_from: NotRequired[datetime | str | None]
    valid_to: NotRequired[datetime | str | None]
    glossary_terms: NotRequired[Sequence[str] | None]
    source_url: NotRequired[str | None]
    language: NotRequired[str | None]
    system_metadata: NotRequired[dict[str, Any] | None]
    created_by: NotRequired[str | None]


def _is_suppressed() -> bool:
    return int(getattr(AspectWriterControl._suppression_depth, "value", 0)) > 0


def _sanitize_urn_id(raw_value: str) -> str:
    text = _ID_SANITIZER.sub("-", str(raw_value or "").strip().lower()).strip("-.:")
    if text:
        return text
    digest = hashlib.sha1(str(raw_value).encode("utf-8")).hexdigest()[:12]
    return f"document-{digest}"


def _truncate_content_text(text: str) -> str:
    content = str(text or "")
    if len(content) <= _MAX_CONTENT_TEXT_CHARS:
        return content
    return content[:_MAX_CONTENT_TEXT_CHARS]


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 4:
        year = int(text)
        if 1900 <= year <= 3000:
            return datetime(year, 1, 1)
    candidate = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _build_document_payload(
    *,
    document_id: str,
    content_text: str,
    instrument_urn: str | None = None,
    valid_from: datetime | str | None = None,
    valid_to: datetime | str | None = None,
    glossary_terms: Sequence[str] | None = None,
    source_url: str | None = None,
    language: str | None = None,
) -> tuple[str, Document]:
    urn = make_urn("document", "prod", _sanitize_urn_id(document_id))
    payload = Document(
        urn=urn,
        instrument_urn=instrument_urn,
        valid_from=_coerce_datetime(valid_from),
        valid_to=_coerce_datetime(valid_to),
        glossary_terms=list(glossary_terms or ()),
        content_text=_truncate_content_text(content_text),
        source_url=source_url,
        language=language,
    )
    return urn, payload


def emit_document_aspect(
    *,
    document_id: str,
    content_text: str,
    instrument_urn: str | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    glossary_terms: Sequence[str] | None = None,
    source_url: str | None = None,
    language: str | None = None,
    system_metadata: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> str:
    """Persist one ``documentMetadata`` aspect and return the document URN."""
    urn, payload = _build_document_payload(
        document_id=document_id,
        content_text=content_text,
        instrument_urn=instrument_urn,
        valid_from=valid_from,
        valid_to=valid_to,
        glossary_terms=glossary_terms,
        source_url=source_url,
        language=language,
    )
    if _is_suppressed():
        return urn
    try:
        with get_session() as session:
            write_aspect(
                session,
                urn,
                "documentMetadata",
                payload,
                created_by=created_by,
                system_metadata=system_metadata,
            )
            session.commit()
    except ImmutableAspectError:
        logger.warning(
            "Document aspect already immutable for urn=%s (id=%s).",
            urn,
            document_id,
        )
        return urn
    logger.info("Emitted documentMetadata aspect urn=%s", urn)
    return urn


def emit_documents_batch(documents: Iterable[DocumentEmissionPayload]) -> list[str]:
    """Persist many ``documentMetadata`` aspects in one DB session."""
    payloads = list(documents)
    if not payloads:
        return []

    to_write: list[tuple[str, Document, str | None, dict[str, Any] | None]] = []
    for item in payloads:
        document_id = str(item.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("document_id cannot be empty")
        urn, payload = _build_document_payload(
            document_id=document_id,
            content_text=str(item.get("content_text") or ""),
            instrument_urn=item.get("instrument_urn"),
            valid_from=item.get("valid_from"),
            valid_to=item.get("valid_to"),
            glossary_terms=item.get("glossary_terms"),
            source_url=item.get("source_url"),
            language=item.get("language"),
        )
        to_write.append((urn, payload, item.get("created_by"), item.get("system_metadata")))

    urns = [urn for urn, _, _, _ in to_write]
    if _is_suppressed():
        return urns

    with get_session() as session:
        for urn, payload, created_by, system_metadata in to_write:
            try:
                write_aspect(
                    session,
                    urn,
                    "documentMetadata",
                    payload,
                    created_by=created_by,
                    system_metadata=system_metadata,
                )
            except ImmutableAspectError:
                logger.warning("Document aspect already immutable for urn=%s.", urn)
        session.commit()
    logger.info("Emitted %d documentMetadata aspects.", len(urns))
    return urns


def extract_glossary_terms(text: str, *, max_terms: int = 16) -> list[str]:
    """Return canonical glossary terms found in ``text``."""
    if max_terms <= 0:
        return []
    candidate_text = str(text or "")
    if not candidate_text:
        return []

    hits: list[tuple[int, int, str]] = []
    for rank, (term, pattern) in enumerate(_FINANCIAL_TERM_PATTERNS):
        match = pattern.search(candidate_text)
        if match is not None:
            hits.append((match.start(), rank, term))
    hits.sort(key=lambda item: (item[0], item[1]))

    out: list[str] = []
    seen: set[str] = set()
    for _, _, term in hits:
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= max_terms:
            break
    return out


__all__ = [
    "DocumentEmissionPayload",
    "emit_document_aspect",
    "emit_documents_batch",
    "extract_glossary_terms",
]
