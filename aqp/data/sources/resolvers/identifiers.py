"""Identifier resolution + upsert.

The :class:`IdentifierResolver` gives every adapter a single place to:

1. resolve ``(scheme, value)`` to a canonical :class:`Instrument` row;
2. upsert new :class:`IdentifierLink` rows when it discovers a new alias
   (CIK, CUSIP, ISIN, FIGI, …) for an existing instrument;
3. return the full identifier graph for an instrument so the UI can
   render a "known identifiers" chip row.

Time-versioning is minimal on purpose: rows are kept forever, a new
``valid_from`` starts a new row, and the unique index on
``(entity_kind, scheme, value, valid_from)`` guarantees idempotence.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select

from aqp.core.domain.identifiers import IdentifierScheme
from aqp.data.sources.base import IdentifierSpec
from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource, IdentifierLink, Instrument

try:
    from aqp.persistence.models_entities import Issuer
except ImportError:  # pragma: no cover — issuer tables not yet migrated
    Issuer = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# Full set of well-known schemes drawn from the expanded
# :class:`aqp.core.domain.identifiers.IdentifierScheme` enum plus the
# legacy names kept for back-compat.
_WELL_KNOWN_SCHEMES: frozenset[str] = frozenset(
    {scheme.value for scheme in IdentifierScheme}
    | {
        # Legacy aliases — kept so older ingestion code keeps working.
        "ticker",
        "vt_symbol",
        "cik",
        "cusip",
        "isin",
        "figi",
        "sedol",
        "lei",
        "gvkey",
        "permid",
        "openfigi",
        "bbg_id",
        "ric",
        "gdelt_theme",
        "fred_series_id",
    }
)


# Schemes that should resolve to an :class:`Issuer` row (instead of an
# :class:`Instrument`) when present.
_ISSUER_SCHEMES: frozenset[str] = frozenset(
    {
        IdentifierScheme.CIK.value,
        IdentifierScheme.LEI.value,
        IdentifierScheme.PERMID.value,
        IdentifierScheme.REFINITIV_PERMID.value,
        IdentifierScheme.GVKEY.value,
        IdentifierScheme.DUNS.value,
        IdentifierScheme.IRS_EIN.value,
        IdentifierScheme.FACTSET_ID.value,
    }
)


class IdentifierResolver:
    """Session-aware CRUD helper for the ``identifier_links`` table."""

    def __init__(self, source_name: str | None = None) -> None:
        self.source_name = source_name

    # ------------------------------------------------------------------
    # Resolution (read path)
    # ------------------------------------------------------------------

    def resolve_instrument(
        self,
        scheme: str,
        value: str,
        *,
        as_of: datetime | None = None,
    ) -> Instrument | None:
        """Return the canonical :class:`Instrument` for ``(scheme, value)``.

        Falls back to the ``instruments.identifiers`` JSON blob and the
        native ``ticker`` / ``vt_symbol`` columns when no
        ``identifier_links`` row exists — keeps old data readable.
        """
        scheme = scheme.lower()
        with get_session() as session:
            row = session.execute(
                select(Instrument)
                .join(
                    IdentifierLink,
                    IdentifierLink.instrument_id == Instrument.id,
                )
                .where(IdentifierLink.scheme == scheme)
                .where(IdentifierLink.value == str(value))
                .where(
                    or_(
                        IdentifierLink.valid_from.is_(None),
                        IdentifierLink.valid_from <= (as_of or datetime.utcnow()),
                    )
                )
                .where(
                    or_(
                        IdentifierLink.valid_to.is_(None),
                        IdentifierLink.valid_to >= (as_of or datetime.utcnow()),
                    )
                )
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
                return row

            # Legacy fallback: native columns + JSON blob.
            if scheme == "ticker":
                row = session.execute(
                    select(Instrument).where(Instrument.ticker == str(value)).limit(1)
                ).scalar_one_or_none()
            elif scheme == "vt_symbol":
                row = session.execute(
                    select(Instrument).where(Instrument.vt_symbol == str(value)).limit(1)
                ).scalar_one_or_none()
            if row is not None:
                session.expunge(row)
                return row
            return None

    def resolve_issuer(
        self,
        scheme: str,
        value: str,
        *,
        as_of: datetime | None = None,
    ) -> Any | None:
        """Return the canonical :class:`Issuer` row for ``(scheme, value)``.

        Only looks at rows where ``entity_kind == "issuer"``; uses the same
        time-versioning semantics as :meth:`resolve_instrument`. Returns
        ``None`` if the ``issuers`` table hasn't been migrated yet or no
        match is found.
        """
        if Issuer is None:
            return None
        scheme = scheme.lower()
        with get_session() as session:
            row = session.execute(
                select(Issuer)
                .join(
                    IdentifierLink,
                    IdentifierLink.entity_id == Issuer.id,
                )
                .where(IdentifierLink.entity_kind == "issuer")
                .where(IdentifierLink.scheme == scheme)
                .where(IdentifierLink.value == str(value))
                .where(
                    or_(
                        IdentifierLink.valid_from.is_(None),
                        IdentifierLink.valid_from <= (as_of or datetime.utcnow()),
                    )
                )
                .where(
                    or_(
                        IdentifierLink.valid_to.is_(None),
                        IdentifierLink.valid_to >= (as_of or datetime.utcnow()),
                    )
                )
                .limit(1)
            ).scalar_one_or_none()

            if row is None:
                # Fallback to denormalized columns on ``issuers``.
                column = getattr(Issuer, scheme, None)
                if column is not None:
                    row = session.execute(
                        select(Issuer).where(column == str(value)).limit(1)
                    ).scalar_one_or_none()

            if row is not None:
                session.expunge(row)
            return row

    def instrument_identifiers(self, instrument_id: str) -> list[dict[str, Any]]:
        """Return every identifier known for ``instrument_id`` as a dict list."""
        with get_session() as session:
            rows = session.execute(
                select(IdentifierLink)
                .where(IdentifierLink.instrument_id == instrument_id)
                .order_by(IdentifierLink.scheme, IdentifierLink.valid_from)
            ).scalars().all()
            return [
                {
                    "id": row.id,
                    "scheme": row.scheme,
                    "value": row.value,
                    "valid_from": row.valid_from,
                    "valid_to": row.valid_to,
                    "source_id": row.source_id,
                    "confidence": row.confidence,
                    "meta": dict(row.meta or {}),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Upsert (write path)
    # ------------------------------------------------------------------

    def upsert_links(
        self,
        specs: Iterable[IdentifierSpec],
        *,
        default_entity_kind: str = "instrument",
    ) -> list[str]:
        """Upsert a list of :class:`IdentifierSpec` rows.

        Returns the list of persisted ``identifier_links.id`` values.
        Silently skips malformed specs (empty scheme or value) rather
        than raising so one bad row doesn't poison a whole ingest.
        """
        specs = [s for s in specs if s and s.scheme and s.value]
        if not specs:
            return []

        source_id = self._source_id(self.source_name)

        persisted: list[str] = []
        with get_session() as session:
            for spec in specs:
                scheme = spec.scheme.lower().strip()
                value = str(spec.value).strip()
                if not scheme or not value:
                    continue
                if scheme not in _WELL_KNOWN_SCHEMES:
                    logger.debug(
                        "identifier_resolver: non-standard scheme %r accepted",
                        scheme,
                    )

                instrument_id = spec.entity_id if spec.entity_kind == "instrument" else None
                if instrument_id is None and spec.instrument_vt_symbol:
                    instrument_id = self._lookup_instrument_id(
                        session, spec.instrument_vt_symbol
                    )

                entity_kind = spec.entity_kind or default_entity_kind
                entity_id = (
                    spec.entity_id
                    or instrument_id
                    or spec.instrument_vt_symbol
                    or value
                )

                # Idempotent check using the unique index.
                existing = session.execute(
                    select(IdentifierLink).where(
                        and_(
                            IdentifierLink.entity_kind == entity_kind,
                            IdentifierLink.scheme == scheme,
                            IdentifierLink.value == value,
                            IdentifierLink.valid_from.is_(spec.valid_from)
                            if spec.valid_from is None
                            else IdentifierLink.valid_from == spec.valid_from,
                        )
                    ).limit(1)
                ).scalar_one_or_none()

                if existing is None:
                    row = IdentifierLink(
                        entity_kind=entity_kind,
                        entity_id=str(entity_id),
                        instrument_id=instrument_id,
                        scheme=scheme,
                        value=value,
                        valid_from=spec.valid_from,
                        valid_to=spec.valid_to,
                        source_id=source_id,
                        confidence=float(spec.confidence or 1.0),
                        meta=dict(spec.meta or {}),
                        created_at=datetime.utcnow(),
                    )
                    session.add(row)
                    session.flush()
                    persisted.append(row.id)
                else:
                    # Patch non-null fields so repeated ingest refines confidence.
                    if instrument_id and not existing.instrument_id:
                        existing.instrument_id = instrument_id
                    if source_id and not existing.source_id:
                        existing.source_id = source_id
                    if spec.valid_to and not existing.valid_to:
                        existing.valid_to = spec.valid_to
                    if spec.confidence and float(spec.confidence) > float(
                        existing.confidence or 0.0
                    ):
                        existing.confidence = float(spec.confidence)
                    if spec.meta:
                        existing.meta = {**(existing.meta or {}), **spec.meta}
                    session.add(existing)
                    persisted.append(existing.id)

                # Write-through to the legacy JSON blob so readers that never
                # migrated to identifier_links still see the alias.
                if instrument_id and scheme in _WELL_KNOWN_SCHEMES:
                    inst = session.get(Instrument, instrument_id)
                    if inst is not None:
                        existing_ids = dict(inst.identifiers or {})
                        if existing_ids.get(scheme) != value:
                            existing_ids[scheme] = value
                            inst.identifiers = existing_ids
                            inst.updated_at = datetime.utcnow()
                            session.add(inst)

            session.flush()
        return persisted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _lookup_instrument_id(session: Any, vt_symbol: str) -> str | None:
        row = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
        ).scalar_one_or_none()
        return row.id if row else None

    @staticmethod
    def _source_id(name: str | None) -> str | None:
        if not name:
            return None
        with get_session() as session:
            row = session.execute(
                select(DataSource).where(DataSource.name == name).limit(1)
            ).scalar_one_or_none()
            return row.id if row else None
