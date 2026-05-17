"""Per-source entity extractors."""
from __future__ import annotations

from aqp.data.entities.extractors.base import EntityExtractor, ExtractionResult
from aqp.data.entities.extractors.filings_extractor import FilingsEntityExtractor
from aqp.data.entities.extractors.finance_database_extractor import (
    FinanceDatabaseEntityExtractor,
)
from aqp.data.entities.extractors.instrument_extractor import (
    InstrumentEntityExtractor,
)
from aqp.data.entities.extractors.news_extractor import NewsEntityExtractor
from aqp.data.entities.extractors.regulatory_extractor import (
    RegulatoryEntityExtractor,
)

EXTRACTOR_REGISTRY: dict[str, type[EntityExtractor]] = {
    "regulatory": RegulatoryEntityExtractor,
    "filings": FilingsEntityExtractor,
    "news": NewsEntityExtractor,
    "instruments": InstrumentEntityExtractor,
    "finance_database": FinanceDatabaseEntityExtractor,
}


def get_extractor(name: str) -> type[EntityExtractor]:
    if name not in EXTRACTOR_REGISTRY:
        raise KeyError(f"unknown extractor {name!r}")
    return EXTRACTOR_REGISTRY[name]


__all__ = [
    "EXTRACTOR_REGISTRY",
    "EntityExtractor",
    "ExtractionResult",
    "FilingsEntityExtractor",
    "FinanceDatabaseEntityExtractor",
    "InstrumentEntityExtractor",
    "NewsEntityExtractor",
    "RegulatoryEntityExtractor",
    "get_extractor",
]
