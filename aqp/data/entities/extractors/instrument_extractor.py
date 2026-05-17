"""Sync existing :class:`Instrument` rows into the unified entity registry."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from aqp.data.entities.extractors.base import EntityCandidate, EntityExtractor


class InstrumentEntityExtractor(EntityExtractor):
    """Map every :class:`Instrument` row to a ``security`` entity."""

    name = "instruments"
    extractor_id = "instruments.sync"

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        for instrument in rows:
            data = self._coerce(instrument)
            vt_symbol = data.get("vt_symbol")
            ticker = data.get("ticker")
            exchange = data.get("exchange")
            if not vt_symbol:
                continue
            identifiers: list[dict[str, Any]] = [
                {"scheme": "vt_symbol", "value": vt_symbol},
            ]
            if ticker:
                identifiers.append({"scheme": "ticker", "value": ticker})
            yield EntityCandidate(
                kind="security",
                canonical_name=vt_symbol,
                short_name=ticker,
                primary_identifier=vt_symbol,
                primary_identifier_scheme="vt_symbol",
                attributes={
                    "exchange": exchange,
                    "asset_class": data.get("asset_class"),
                    "security_type": data.get("security_type"),
                    "sector": data.get("sector"),
                    "industry": data.get("industry"),
                    "currency": data.get("currency"),
                },
                tags=["instrument"],
                confidence=1.0,
                instrument_id=data.get("id"),
                identifiers=identifiers,
            )

    @staticmethod
    def _coerce(instrument: Any) -> dict[str, Any]:
        if isinstance(instrument, dict):
            return instrument
        return {
            "id": getattr(instrument, "id", None),
            "vt_symbol": getattr(instrument, "vt_symbol", None),
            "ticker": getattr(instrument, "ticker", None),
            "exchange": getattr(instrument, "exchange", None),
            "asset_class": getattr(instrument, "asset_class", None),
            "security_type": getattr(instrument, "security_type", None),
            "sector": getattr(instrument, "sector", None),
            "industry": getattr(instrument, "industry", None),
            "currency": getattr(instrument, "currency", None),
        }
