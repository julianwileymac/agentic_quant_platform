"""Extract entities from SEC EDGAR filings."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from aqp.data.entities.extractors.base import EntityCandidate, EntityExtractor


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


class FilingsEntityExtractor(EntityExtractor):
    """Extract company entities from SEC filing index rows.

    Each row is expected to have ``cik``, ``company`` (or ``name``),
    ``form_type``, and optionally ``ticker``.
    """

    name = "filings"
    extractor_id = "filings.sec"

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        for row in rows:
            data = row if isinstance(row, dict) else dict(row)
            cik = _str(data.get("cik"))
            company = _str(data.get("company") or data.get("name"))
            ticker = _str(data.get("ticker"))
            form = _str(data.get("form") or data.get("form_type"))
            if not company and not cik:
                continue

            identifiers: list[dict[str, Any]] = []
            if cik:
                identifiers.append({"scheme": "cik", "value": cik})
            if ticker:
                identifiers.append({"scheme": "ticker", "value": ticker})

            yield EntityCandidate(
                kind="company",
                canonical_name=company or f"CIK {cik}",
                short_name=ticker,
                primary_identifier=cik,
                primary_identifier_scheme="cik",
                attributes={
                    "last_form": form,
                    "ticker": ticker,
                    "filing_date": _str(data.get("date") or data.get("filing_date")),
                },
                tags=["filings", "sec"],
                confidence=0.95,
                identifiers=identifiers,
            )
