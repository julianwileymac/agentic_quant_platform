"""Match GDelt GKG rows against registered instruments.

Given the ``v2_enhanced_organizations`` (or ``v1_organizations``) field
on a GKG row, the :class:`SubjectFilter` attempts to resolve each
organization name against the :class:`Instrument` registry so the
downstream sink can keep only the rows that actually mention a security
the user cares about.

Matching is conservative: exact normalised string match on:

* ``instrument.ticker`` (uppercase, no dots)
* ``instrument.meta["name"]`` when present
* any :class:`IdentifierLink` value with scheme ``"company"``

Partial / fuzzy matching is left as a follow-up so one bad false
positive doesn't snowball into "AAPL mentioned on every page".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select

from aqp.data.sources.gdelt.schema import split_semicolon
from aqp.persistence.db import get_session
from aqp.persistence.models import IdentifierLink, Instrument

logger = logging.getLogger(__name__)


_NORMALISE_RE = re.compile(r"[^A-Z0-9]")


def _normalise(value: str) -> str:
    return _NORMALISE_RE.sub("", str(value or "").upper())


@dataclass(frozen=True)
class SubjectMatch:
    instrument_id: str
    vt_symbol: str
    ticker: str
    matched_on: str
    source_value: str


class SubjectFilter:
    """Loads the instrument registry and matches GKG organisation strings."""

    def __init__(
        self,
        *,
        tickers: Iterable[str] | None = None,
        include_names: bool = True,
    ) -> None:
        self._only_tickers = {t.upper() for t in (tickers or []) if t}
        self._include_names = include_names
        self._index: dict[str, SubjectMatch] = {}

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def load(self) -> int:
        """Populate the in-memory index from the database."""
        self._index.clear()
        with get_session() as session:
            instruments = session.execute(select(Instrument)).scalars().all()
            for inst in instruments:
                ticker = (inst.ticker or "").upper()
                if not ticker:
                    continue
                if self._only_tickers and ticker not in self._only_tickers:
                    continue
                vt_symbol = inst.vt_symbol or f"{ticker}.NASDAQ"
                keys = {ticker}
                ids = dict(inst.identifiers or {})
                for scheme in ("cik", "cusip", "isin", "figi", "lei"):
                    value = ids.get(scheme)
                    if value:
                        keys.add(str(value).upper())
                if self._include_names:
                    name = (inst.meta or {}).get("name") or (inst.meta or {}).get("long_name")
                    if name:
                        keys.add(str(name).upper())
                for key in keys:
                    norm = _normalise(key)
                    if len(norm) < 2:
                        continue
                    self._index.setdefault(
                        norm,
                        SubjectMatch(
                            instrument_id=inst.id,
                            vt_symbol=vt_symbol,
                            ticker=ticker,
                            matched_on="seed",
                            source_value=key,
                        ),
                    )
            # Also index custom identifier_links with scheme=="company".
            links = session.execute(
                select(IdentifierLink).where(IdentifierLink.scheme == "company")
            ).scalars().all()
            for link in links:
                if not link.instrument_id:
                    continue
                inst = session.get(Instrument, link.instrument_id)
                if inst is None:
                    continue
                ticker = (inst.ticker or "").upper()
                if self._only_tickers and ticker not in self._only_tickers:
                    continue
                norm = _normalise(link.value)
                if len(norm) < 2:
                    continue
                self._index.setdefault(
                    norm,
                    SubjectMatch(
                        instrument_id=inst.id,
                        vt_symbol=inst.vt_symbol,
                        ticker=ticker,
                        matched_on="identifier_link",
                        source_value=link.value,
                    ),
                )
        return len(self._index)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match_organizations(self, raw_field: str | None) -> list[SubjectMatch]:
        """Return every :class:`SubjectMatch` found in a GDelt organizations cell."""
        if not raw_field:
            return []
        if not self._index:
            self.load()
        matches: dict[str, SubjectMatch] = {}
        for org in split_semicolon(raw_field):
            name = _strip_offset(org)
            if not name:
                continue
            norm = _normalise(name)
            if not norm:
                continue
            hit = self._index.get(norm)
            if hit is not None:
                matches.setdefault(hit.instrument_id, hit)
        return list(matches.values())


def _strip_offset(value: str) -> str:
    """GKG ``v2_enhanced_organizations`` entries are ``"Name,offset"``."""
    if "," in value:
        value = value.rsplit(",", 1)[0]
    return value.strip()
