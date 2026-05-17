"""Extract entities from a FinanceDatabase taxonomy table."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from aqp.data.entities.extractors.base import EntityCandidate, EntityExtractor


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    return s


class FinanceDatabaseEntityExtractor(EntityExtractor):
    """Map FinanceDatabase rows -> entity candidates.

    ``asset_kind`` selects how rows are mapped:

    - ``equities``  -> ``security`` + ``company`` entity per symbol.
    - ``etfs``      -> ``security`` (kind=etf).
    - ``funds``     -> ``security`` (kind=fund).
    - ``indices``   -> ``index`` entity.
    - ``currencies`` -> ``currency`` entity.
    - ``cryptos``   -> ``security`` (kind=crypto).
    """

    name = "finance_database"
    extractor_id = "finance_database"

    def __init__(self, *, asset_kind: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.asset_kind = (asset_kind or "equities").lower()
        self.extractor_id = f"finance_database.{self.asset_kind}"

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        for row in rows:
            data = row if isinstance(row, dict) else dict(row)
            symbol = _str(data.get("symbol"))
            if not symbol:
                continue
            name = _str(data.get("name"))
            country = _str(data.get("country"))
            sector = _str(data.get("sector"))
            industry = _str(data.get("industry"))
            currency = _str(data.get("currency"))
            isin = _str(data.get("isin"))
            cusip = _str(data.get("cusip"))
            figi = _str(data.get("figi") or data.get("composite_figi"))

            identifiers: list[dict[str, Any]] = [
                {"scheme": "ticker", "value": symbol}
            ]
            if isin:
                identifiers.append({"scheme": "isin", "value": isin})
            if cusip:
                identifiers.append({"scheme": "cusip", "value": cusip})
            if figi:
                identifiers.append({"scheme": "figi", "value": figi})

            sub_kind_map = {
                "etfs": "etf",
                "funds": "fund",
                "cryptos": "crypto",
                "currencies": "currency",
                "indices": "index",
                "moneymarkets": "money_market",
            }
            sec_kind = sub_kind_map.get(self.asset_kind, "security")

            attributes = {
                "country": country,
                "sector": sector,
                "industry": industry,
                "currency": currency,
                "exchange": _str(data.get("exchange")),
                "market": _str(data.get("market")),
                "asset_kind": self.asset_kind,
                "isin": isin,
                "cusip": cusip,
                "figi": figi,
            }

            yield EntityCandidate(
                kind=sec_kind,
                canonical_name=symbol,
                short_name=name,
                primary_identifier=symbol,
                primary_identifier_scheme="ticker",
                attributes={k: v for k, v in attributes.items() if v},
                tags=["finance_database", self.asset_kind],
                confidence=0.9,
                identifiers=identifiers,
            )

            if self.asset_kind == "equities" and name:
                yield EntityCandidate(
                    kind="company",
                    canonical_name=name,
                    short_name=symbol,
                    attributes={
                        "ticker": symbol,
                        "country": country,
                        "sector": sector,
                        "industry": industry,
                    },
                    tags=["finance_database", "company"],
                    confidence=0.85,
                )
