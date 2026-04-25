"""DataDomain taxonomy for the expanded data plane.

Before the data-plane expansion, :class:`DatasetCatalog.domain` was a
free-form string with ``"market.bars"`` as the de-facto default. This
module standardises the known domains so the new adapters and the UI
can reason about them as enum values without breaking older rows that
still use the free-form strings — those simply don't match any enum and
fall back to treating the domain as a raw string.
"""
from __future__ import annotations

from enum import StrEnum


class DataDomain(StrEnum):
    """Well-known AQP data domains.

    Values deliberately use ``.`` as the separator so they sort and
    filter cleanly in UIs ("everything under ``market.*``"). Expanded as
    part of the domain-model expansion to cover every flow the
    :mod:`aqp.providers` catalog exposes (fundamentals, ownership,
    estimates, calendar, macro, ESG, alternative data, options, futures).
    """

    # Market microstructure (existing)
    MARKET_BARS = "market.bars"
    MARKET_QUOTES = "market.quotes"
    MARKET_TICKS = "market.ticks"
    MARKET_FUNDAMENTALS = "market.fundamentals"
    MARKET_SNAPSHOTS = "market.snapshots"

    # Economic / macro
    ECONOMIC_SERIES = "economic.series"
    MACRO_FED = "macro.fed"
    MACRO_TREASURY = "macro.treasury"
    MACRO_PRICES = "macro.prices"
    MACRO_EMPLOYMENT = "macro.employment"
    MACRO_GDP = "macro.gdp"
    MACRO_MONEY = "macro.money"
    MACRO_YIELD_CURVE = "macro.yield_curve"
    MACRO_COT = "macro.cot"
    MACRO_HOUSING = "macro.housing"
    MACRO_BLS = "macro.bls"
    MACRO_ECB = "macro.ecb"
    MACRO_BALANCE_OF_PAYMENTS = "macro.balance_of_payments"

    # Filings (existing + expanded)
    FILINGS_INDEX = "filings.index"
    FILINGS_XBRL = "filings.xbrl"
    FILINGS_INSIDER = "filings.insider"
    FILINGS_OWNERSHIP = "filings.ownership"
    FILINGS_EVENTS = "filings.events"
    FILINGS_13F = "filings.13f"

    # Fundamentals
    FUNDAMENTALS_STATEMENTS = "fundamentals.statements"
    FUNDAMENTALS_RATIOS = "fundamentals.ratios"
    FUNDAMENTALS_METRICS = "fundamentals.metrics"
    FUNDAMENTALS_TRANSCRIPTS = "fundamentals.transcripts"
    FUNDAMENTALS_MDA = "fundamentals.mda"
    FUNDAMENTALS_REVENUE_BREAKDOWN = "fundamentals.revenue_breakdown"
    FUNDAMENTALS_MARKET_CAP = "fundamentals.market_cap"
    FUNDAMENTALS_HISTORICAL_EPS = "fundamentals.historical_eps"
    FUNDAMENTALS_HISTORICAL_DIVIDENDS = "fundamentals.historical_dividends"
    FUNDAMENTALS_HISTORICAL_SPLITS = "fundamentals.historical_splits"

    # Ownership
    OWNERSHIP_INSIDER = "ownership.insider"
    OWNERSHIP_INSTITUTIONAL = "ownership.institutional"
    OWNERSHIP_13F = "ownership.13f"
    OWNERSHIP_SHORT = "ownership.short"
    OWNERSHIP_FLOAT = "ownership.float"
    OWNERSHIP_FTD = "ownership.ftd"
    OWNERSHIP_GOVERNMENT = "ownership.government"
    OWNERSHIP_RETAIL = "ownership.retail"
    OWNERSHIP_PEERS = "ownership.peers"

    # Estimates
    ESTIMATES_ANALYST = "estimates.analyst"
    ESTIMATES_FORWARD = "estimates.forward"
    ESTIMATES_PRICE_TARGET = "estimates.price_target"

    # Calendars
    CALENDAR_EARNINGS = "calendar.earnings"
    CALENDAR_DIVIDEND = "calendar.dividend"
    CALENDAR_SPLIT = "calendar.split"
    CALENDAR_IPO = "calendar.ipo"
    CALENDAR_ECONOMIC = "calendar.economic"

    # News / sentiment
    NEWS = "news"
    NEWS_COMPANY = "news.company"
    NEWS_WORLD = "news.world"
    NEWS_SENTIMENT = "news.sentiment"
    SOCIAL_SENTIMENT = "social.sentiment"

    # ESG
    ESG_SCORE = "esg.score"
    ESG_RISK = "esg.risk"

    # Options / futures / bonds / fx / crypto specifics
    OPTIONS_CHAIN = "options.chain"
    OPTIONS_SNAPSHOT = "options.snapshot"
    OPTIONS_UNUSUAL = "options.unusual"
    OPTIONS_GREEKS = "options.greeks"
    FUTURES_CURVE = "futures.curve"
    FUTURES_HISTORICAL = "futures.historical"
    BONDS_REFERENCE = "bonds.reference"
    BONDS_PRICES = "bonds.prices"
    BONDS_TRADES = "bonds.trades"
    BONDS_INDICES = "bonds.indices"
    FX_PAIRS = "fx.pairs"
    FX_HISTORICAL = "fx.historical"
    FX_REFERENCE_RATES = "fx.reference_rates"
    CRYPTO_SEARCH = "crypto.search"
    CRYPTO_HISTORICAL = "crypto.historical"

    # Reference
    REFERENCE_EQUITY_INFO = "reference.equity_info"
    REFERENCE_ETF_INFO = "reference.etf_info"
    REFERENCE_INDEX_INFO = "reference.index_info"
    REFERENCE_FUTURES_INFO = "reference.futures_info"
    REFERENCE_BOND_REFERENCE = "reference.bond_reference"
    REFERENCE_SYMBOL_MAP = "reference.symbol_map"
    REFERENCE_CIK_MAP = "reference.cik_map"

    # Alternative data
    EVENTS_GDELT = "events.gdelt"
    CORPORATE_ACTIONS = "corporate_actions"
    ALTERNATIVE_MARITIME = "alternative.maritime"
    ALTERNATIVE_PORT_VOLUME = "alternative.port_volume"
    ALTERNATIVE_WEATHER = "alternative.weather"
    ALTERNATIVE_ENERGY = "alternative.energy"
    ALTERNATIVE_AGRICULTURE = "alternative.agriculture"

    # Market status / holidays
    MARKET_STATUS = "market.status"
    MARKET_HOLIDAYS = "market.holidays"

    # Sectors / classifications / performance
    SECTOR_PERFORMANCE = "sector.performance"
    SECTOR_PE = "sector.pe"
    INDUSTRY_PE = "industry.pe"

    @classmethod
    def parse(cls, value: str | "DataDomain" | None) -> "DataDomain | str | None":
        """Return the enum value if known, else the input string unchanged.

        This keeps backwards compatibility with legacy free-form domains
        (e.g. ``"custom.foo"``) while still giving callers the enum type
        when they pass a known value.
        """
        if value is None:
            return None
        if isinstance(value, DataDomain):
            return value
        try:
            return cls(value)
        except ValueError:
            return value


FILINGS_DOMAINS: frozenset[DataDomain] = frozenset(
    {
        DataDomain.FILINGS_INDEX,
        DataDomain.FILINGS_XBRL,
        DataDomain.FILINGS_INSIDER,
        DataDomain.FILINGS_OWNERSHIP,
        DataDomain.FILINGS_EVENTS,
    }
)

MARKET_DOMAINS: frozenset[DataDomain] = frozenset(
    {
        DataDomain.MARKET_BARS,
        DataDomain.MARKET_QUOTES,
        DataDomain.MARKET_TICKS,
        DataDomain.MARKET_FUNDAMENTALS,
    }
)
