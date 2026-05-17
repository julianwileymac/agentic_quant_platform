"""Entity-centric data products (Gold-layer agent context packs).

A :class:`BaseDataProduct` is a pre-aggregated, read-only view over
Silver / Gold tables that:

- Aggregates everything the LLM needs about one business entity into
  a single object
- Hides table joins / Postgres reads behind a clean
  :meth:`to_context_pack` interface that respects a token budget
- Surfaces lineage + provenance + quality metrics directly so the
  agent can reason about *why* it should trust the data

Concrete products:

- :class:`EquityEntity` — instrument + bars + fundamentals + ratios + news
- :class:`OptionChainEntity` — chain snapshot + IV surface
- :class:`PortfolioEntity` — positions + exposures + fills + risk
- :class:`MacroSeriesEntity` — FRED / BLS / Treasury series + observations
- :class:`RegulatoryEntity` — CFPB / FDA / USPTO mentions
- :class:`InstrumentGraphProduct` — entity graph walk
"""
from __future__ import annotations

from aqp.data.products.base import (
    BaseDataProduct,
    DataProductError,
    DataProvenance,
    DataQuality,
    LineageBreadcrumb,
)
from aqp.data.products.equity import EquityEntity
from aqp.data.products.instrument_graph import InstrumentGraphProduct
from aqp.data.products.macro_series import MacroSeriesEntity
from aqp.data.products.option_chain import OptionChainEntity
from aqp.data.products.portfolio import PortfolioEntity
from aqp.data.products.regulatory import RegulatoryEntity

__all__ = [
    "BaseDataProduct",
    "DataProductError",
    "DataProvenance",
    "DataQuality",
    "EquityEntity",
    "InstrumentGraphProduct",
    "LineageBreadcrumb",
    "MacroSeriesEntity",
    "OptionChainEntity",
    "PortfolioEntity",
    "RegulatoryEntity",
]
