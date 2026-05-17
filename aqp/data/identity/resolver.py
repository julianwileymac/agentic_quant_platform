"""Temporal identifier resolution against the normalized ``identifier_links`` table.

The resolver walks the time-versioned alias graph in
:class:`aqp.persistence.models.IdentifierLink` to answer two questions:

1. "What is the CUSIP for AAPL as of 2018-06-12?" -- forward resolution
2. "Give me every identifier known for instrument ``X``, ordered by
   validity start" -- history walk

Both questions are answered with a single index scan thanks to the
``ix_identifier_links_scheme_value`` and
``ix_identifier_links_entity`` composite indexes on the persistence row.

The functions stay deliberately thin: the heavy lifting is the SQL
filter combining ``valid_from <= as_of`` and ``(valid_to IS NULL OR
valid_to > as_of)``. NULL bounds mean "valid for all time the row
represents" -- the convention the legacy JSON blob backfill in
migration 0040 uses for rows it imported.

Hard-rule compliance:

* AGENTS rule 22 -- this module is imported by
  :mod:`aqp.data.mcp.tools.identity` so agent reads never touch ORM
  directly.
* AGENTS rule 5 -- the resolver returns plain dataclasses, not ORM
  instances, so callers can safely pass results across Celery workers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import and_, or_, select

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IdentifierResolution:
    """Result of a forward identifier lookup.

    Carries both the resolved row and its validity window so callers
    can decide whether the resolution is "stable" enough for use in a
    long-running backtest (multiple-year window) or just a snapshot
    (point-in-time backtest).
    """

    entity_kind: str
    entity_id: str
    instrument_id: str | None
    scheme: str
    value: str
    valid_from: datetime | None
    valid_to: datetime | None
    confidence: float
    source_id: str | None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open_ended(self) -> bool:
        """True when ``valid_to`` is NULL ("still valid")."""
        return self.valid_to is None

    def to_json(self) -> dict[str, Any]:
        return {
            "entity_kind": self.entity_kind,
            "entity_id": self.entity_id,
            "instrument_id": self.instrument_id,
            "scheme": self.scheme,
            "value": self.value,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "confidence": float(self.confidence),
            "source_id": self.source_id,
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class IdentifierHistoryRow:
    """One row in an identifier-history walk.

    Ordered chronologically when emitted by :func:`IdentifierResolver.history`;
    spans with NULL ``valid_from`` come first (oldest), spans with NULL
    ``valid_to`` come last (still-current).
    """

    scheme: str
    value: str
    valid_from: datetime | None
    valid_to: datetime | None
    confidence: float

    def to_json(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "value": self.value,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "confidence": float(self.confidence),
        }


class IdentifierResolver:
    """Temporal resolver over the ``identifier_links`` alias graph.

    Sessions are obtained from :func:`aqp.persistence.db.get_session` so
    every call participates in the standard sync transaction lifecycle.
    Asynchronous callers (FastAPI routes) should wrap calls in
    ``asyncio.to_thread`` -- the resolver is intentionally synchronous
    because the row volume per query is small (single-digit rows for
    most lookups) and the per-call overhead is dominated by index lookup.
    """

    def __init__(self, *, default_entity_kind: str = "instrument") -> None:
        self._default_entity_kind = default_entity_kind

    # ------------------------------------------------------------------
    # Forward resolution
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        scheme: str,
        value: str,
        as_of: datetime | None = None,
        entity_kind: str | None = None,
        instrument_id: str | None = None,
    ) -> IdentifierResolution | None:
        """Resolve ``(scheme, value)`` to its row valid at ``as_of``.

        Returns the highest-confidence row that satisfies the validity
        predicate, or ``None`` when no such row exists. ``as_of`` defaults
        to ``datetime.utcnow()`` for "right now" lookups (most live
        trading code paths).

        ``entity_kind`` restricts the search (instrument, fred_series,
        sec_filing, gdelt_theme, company); the default is
        :attr:`_default_entity_kind`. ``instrument_id`` is an extra
        scope when the caller already knows the parent instrument and
        just wants the alias.
        """
        from aqp.persistence.db import get_session
        from aqp.persistence.models import IdentifierLink

        as_of_ts = as_of or datetime.utcnow()
        kind = entity_kind or self._default_entity_kind
        scheme_norm = scheme.strip().lower()
        value_norm = str(value).strip()
        if not scheme_norm or not value_norm:
            return None

        with get_session() as session:
            stmt = (
                select(IdentifierLink)
                .where(
                    IdentifierLink.entity_kind == kind,
                    IdentifierLink.scheme == scheme_norm,
                    IdentifierLink.value == value_norm,
                )
                .where(
                    or_(
                        IdentifierLink.valid_from.is_(None),
                        IdentifierLink.valid_from <= as_of_ts,
                    )
                )
                .where(
                    or_(
                        IdentifierLink.valid_to.is_(None),
                        IdentifierLink.valid_to > as_of_ts,
                    )
                )
                .order_by(IdentifierLink.confidence.desc())
            )
            if instrument_id is not None:
                stmt = stmt.where(IdentifierLink.instrument_id == instrument_id)
            row = session.execute(stmt).scalars().first()
            if row is None:
                return None
            return _row_to_resolution(row)

    def resolve_to_instrument(
        self,
        *,
        scheme: str,
        value: str,
        as_of: datetime | None = None,
    ) -> str | None:
        """Return the ``instrument_id`` an alias resolves to at ``as_of``."""
        res = self.resolve(scheme=scheme, value=value, as_of=as_of)
        return None if res is None else res.instrument_id

    # ------------------------------------------------------------------
    # History walk
    # ------------------------------------------------------------------

    def history(
        self,
        *,
        entity_kind: str,
        entity_id: str,
        scheme: str | None = None,
    ) -> list[IdentifierHistoryRow]:
        """Return every known alias for ``(entity_kind, entity_id)``.

        Sorted chronologically (NULL ``valid_from`` first, NULL
        ``valid_to`` last). ``scheme`` filters to a single namespace
        (e.g. CUSIP-history only).
        """
        from aqp.persistence.db import get_session
        from aqp.persistence.models import IdentifierLink

        with get_session() as session:
            stmt = (
                select(IdentifierLink)
                .where(IdentifierLink.entity_kind == entity_kind)
                .where(IdentifierLink.entity_id == entity_id)
            )
            if scheme:
                stmt = stmt.where(IdentifierLink.scheme == scheme.strip().lower())
            rows = session.execute(stmt).scalars().all()

        def _sort_key(r: Any) -> tuple[int, datetime, int, datetime]:
            vf = r.valid_from
            vt = r.valid_to
            return (
                0 if vf is None else 1,
                vf or datetime.min,
                0 if vt is None else 1,
                vt or datetime.max,
            )

        rows_sorted = sorted(rows, key=_sort_key)
        return [
            IdentifierHistoryRow(
                scheme=r.scheme,
                value=r.value,
                valid_from=r.valid_from,
                valid_to=r.valid_to,
                confidence=float(r.confidence or 0.0),
            )
            for r in rows_sorted
        ]

    # ------------------------------------------------------------------
    # Bulk forward lookup (used by ingestion paths)
    # ------------------------------------------------------------------

    def bulk_resolve_to_instrument(
        self,
        pairs: Iterable[tuple[str, str]],
        *,
        as_of: datetime | None = None,
    ) -> dict[tuple[str, str], str]:
        """Bulk-resolve a list of ``(scheme, value)`` pairs to instrument ids.

        Single round-trip with a UNION-friendly OR filter; useful when an
        ingestion job has a manifest of identifiers and needs to map
        them all in one pass.
        """
        from aqp.persistence.db import get_session
        from aqp.persistence.models import IdentifierLink

        items = [
            (s.strip().lower(), str(v).strip()) for s, v in pairs if s and v is not None
        ]
        if not items:
            return {}

        as_of_ts = as_of or datetime.utcnow()
        clauses = [
            and_(IdentifierLink.scheme == s, IdentifierLink.value == v)
            for s, v in items
        ]
        with get_session() as session:
            stmt = (
                select(IdentifierLink)
                .where(or_(*clauses))
                .where(
                    or_(
                        IdentifierLink.valid_from.is_(None),
                        IdentifierLink.valid_from <= as_of_ts,
                    )
                )
                .where(
                    or_(
                        IdentifierLink.valid_to.is_(None),
                        IdentifierLink.valid_to > as_of_ts,
                    )
                )
                .order_by(IdentifierLink.confidence.desc())
            )
            rows = session.execute(stmt).scalars().all()

        out: dict[tuple[str, str], str] = {}
        for r in rows:
            key = (r.scheme, r.value)
            if key not in out and r.instrument_id:
                out[key] = r.instrument_id
        return out


# ---------------------------------------------------------------------------
# Module-level convenience helpers (the MCP tools call these directly).
# ---------------------------------------------------------------------------


_DEFAULT_RESOLVER = IdentifierResolver()


def resolve(
    *,
    scheme: str,
    value: str,
    as_of: datetime | None = None,
    entity_kind: str | None = None,
    instrument_id: str | None = None,
) -> IdentifierResolution | None:
    """Module-level shim for :meth:`IdentifierResolver.resolve`."""
    return _DEFAULT_RESOLVER.resolve(
        scheme=scheme,
        value=value,
        as_of=as_of,
        entity_kind=entity_kind,
        instrument_id=instrument_id,
    )


def resolve_to_instrument(
    *,
    scheme: str,
    value: str,
    as_of: datetime | None = None,
) -> str | None:
    """Module-level shim for :meth:`IdentifierResolver.resolve_to_instrument`."""
    return _DEFAULT_RESOLVER.resolve_to_instrument(
        scheme=scheme, value=value, as_of=as_of
    )


def history(
    *,
    entity_kind: str,
    entity_id: str,
    scheme: str | None = None,
) -> list[IdentifierHistoryRow]:
    """Module-level shim for :meth:`IdentifierResolver.history`."""
    return _DEFAULT_RESOLVER.history(
        entity_kind=entity_kind, entity_id=entity_id, scheme=scheme
    )


def _row_to_resolution(row: Any) -> IdentifierResolution:
    return IdentifierResolution(
        entity_kind=row.entity_kind,
        entity_id=row.entity_id,
        instrument_id=row.instrument_id,
        scheme=row.scheme,
        value=row.value,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        confidence=float(row.confidence or 0.0),
        source_id=row.source_id,
        meta=dict(row.meta or {}),
    )


__all__ = [
    "IdentifierHistoryRow",
    "IdentifierResolution",
    "IdentifierResolver",
    "history",
    "resolve",
    "resolve_to_instrument",
]
