"""Feature catalog — turn data feed fields into discoverable feature candidates.

The Web UI's Feature Set Workbench needs a way to browse every field that
the platform's data feeds can emit (Alpha Vantage overview metrics, FRED
macro series, GDelt event tone, …) so users can drop them into a feature
spec without having to remember the exact column name.

This module walks the OpenBB-style providers in :mod:`aqp.providers.catalog`
and the data-source registry in :mod:`aqp.data.sources.registry`, plus a
curated static list for popular Alpha Vantage / FRED / SEC / GDelt
fields, and produces a flat list of :class:`FeatureCandidate` records.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FeatureCandidate:
    """A single feed-provided field a user can wire into a feature set."""

    id: str
    source: str  # e.g. "alpha_vantage", "fred", "yfinance"
    domain: str  # e.g. "fundamentals.overview", "macro.series"
    field: str
    description: str = ""
    dtype: str = "float"
    frequency: str = "daily"
    unit: str | None = None


# ---------------------------------------------------------------------------
# Curated catalog. Hand-picked so the UI gets a useful default even when
# providers aren't wired into the catalog yet.
# ---------------------------------------------------------------------------

_AV_OVERVIEW_FIELDS: list[tuple[str, str]] = [
    ("MarketCapitalization", "Market capitalization (USD)"),
    ("EBITDA", "EBITDA"),
    ("PERatio", "Price-to-earnings ratio"),
    ("PEGRatio", "PEG ratio"),
    ("BookValue", "Book value per share"),
    ("DividendYield", "Trailing dividend yield"),
    ("EPS", "Trailing EPS"),
    ("RevenuePerShareTTM", "Revenue per share TTM"),
    ("ProfitMargin", "Profit margin"),
    ("OperatingMarginTTM", "Operating margin TTM"),
    ("ReturnOnAssetsTTM", "ROA TTM"),
    ("ReturnOnEquityTTM", "ROE TTM"),
    ("RevenueTTM", "Revenue TTM"),
    ("GrossProfitTTM", "Gross profit TTM"),
    ("Beta", "Equity beta"),
    ("52WeekHigh", "52 week high"),
    ("52WeekLow", "52 week low"),
    ("50DayMovingAverage", "50-day moving average"),
    ("200DayMovingAverage", "200-day moving average"),
    ("SharesOutstanding", "Shares outstanding"),
]


_AV_NEWS_FIELDS: list[tuple[str, str]] = [
    ("overall_sentiment_score", "Aggregate sentiment score across the article window"),
    ("overall_sentiment_label", "Sentiment label (Bullish / Neutral / Bearish)"),
    ("ticker_sentiment_score", "Ticker-specific sentiment score"),
    ("relevance_score", "Relevance score for the article-ticker pair"),
]


_AV_INSIDER_FIELDS: list[tuple[str, str]] = [
    ("net_insider_volume", "Net insider purchase volume"),
    ("insider_buys", "Number of insider buys"),
    ("insider_sells", "Number of insider sells"),
]


_AV_TIMESERIES_FIELDS: list[tuple[str, str]] = [
    ("adjusted_close", "Dividend/split-adjusted close"),
    ("dividend_amount", "Dividend amount"),
    ("split_coefficient", "Split coefficient"),
]


_FRED_SERIES: list[tuple[str, str, str]] = [
    ("DGS10", "10-year Treasury constant maturity yield", "daily"),
    ("DGS2", "2-year Treasury constant maturity yield", "daily"),
    ("DTB3", "3-month Treasury bill secondary market", "daily"),
    ("T10Y2Y", "10y-2y Treasury yield spread", "daily"),
    ("VIXCLS", "CBOE Volatility Index", "daily"),
    ("BAMLH0A0HYM2", "ICE BofA US High Yield OAS", "daily"),
    ("DEXUSEU", "USD/EUR exchange rate", "daily"),
    ("CPIAUCSL", "CPI All Urban Consumers", "monthly"),
    ("UNRATE", "Civilian unemployment rate", "monthly"),
    ("INDPRO", "Industrial production index", "monthly"),
    ("PAYEMS", "Total nonfarm payrolls", "monthly"),
    ("FEDFUNDS", "Effective federal funds rate", "monthly"),
    ("M2SL", "M2 money stock", "monthly"),
    ("HOUST", "Housing starts", "monthly"),
    ("UMCSENT", "U. of Michigan: Consumer Sentiment", "monthly"),
]


_GDELT_FIELDS: list[tuple[str, str]] = [
    ("AvgTone", "Average article tone (-100 to +100)"),
    ("EventCount", "Article volume per (entity, day)"),
    ("GoldsteinScale", "Goldstein conflict-cooperation score"),
    ("NumMentions", "Number of mentions in news"),
    ("NumSources", "Number of distinct news sources"),
]


_SEC_FIELDS: list[tuple[str, str]] = [
    ("filing.cik", "Central Index Key"),
    ("filing.form_type", "Form type (10-K, 10-Q, 8-K, …)"),
    ("filing.filed_at", "Filing acceptance timestamp"),
    ("filing.is_xbrl", "Filing is XBRL-tagged"),
    ("financials.totalRevenue", "Total revenue (XBRL)"),
    ("financials.netIncomeLoss", "Net income / loss (XBRL)"),
    ("financials.cashAndCashEquivalents", "Cash and equivalents (XBRL)"),
]


def _av_candidates() -> list[FeatureCandidate]:
    out: list[FeatureCandidate] = []
    for f, desc in _AV_OVERVIEW_FIELDS:
        out.append(
            FeatureCandidate(
                id=f"alpha_vantage.fundamentals.overview.{f}",
                source="alpha_vantage",
                domain="fundamentals.overview",
                field=f,
                description=desc,
                frequency="daily",
            )
        )
    for f, desc in _AV_NEWS_FIELDS:
        out.append(
            FeatureCandidate(
                id=f"alpha_vantage.news.sentiment.{f}",
                source="alpha_vantage",
                domain="news.sentiment",
                field=f,
                description=desc,
                frequency="hourly",
            )
        )
    for f, desc in _AV_INSIDER_FIELDS:
        out.append(
            FeatureCandidate(
                id=f"alpha_vantage.insider.transactions.{f}",
                source="alpha_vantage",
                domain="insider.transactions",
                field=f,
                description=desc,
                frequency="daily",
            )
        )
    for f, desc in _AV_TIMESERIES_FIELDS:
        out.append(
            FeatureCandidate(
                id=f"alpha_vantage.market.bars.{f}",
                source="alpha_vantage",
                domain="market.bars",
                field=f,
                description=desc,
                frequency="daily",
            )
        )
    return out


def _fred_candidates() -> list[FeatureCandidate]:
    return [
        FeatureCandidate(
            id=f"fred.macro.series.{code}",
            source="fred",
            domain="macro.series",
            field=code,
            description=desc,
            frequency=freq,
        )
        for code, desc, freq in _FRED_SERIES
    ]


def _gdelt_candidates() -> list[FeatureCandidate]:
    return [
        FeatureCandidate(
            id=f"gdelt.news.events.{f}",
            source="gdelt",
            domain="news.events",
            field=f,
            description=desc,
            frequency="hourly",
        )
        for f, desc in _GDELT_FIELDS
    ]


def _sec_candidates() -> list[FeatureCandidate]:
    return [
        FeatureCandidate(
            id=f"sec.{f.split('.', 1)[0]}.{f.split('.', 1)[1]}",
            source="sec",
            domain=f.split(".", 1)[0],
            field=f.split(".", 1)[1],
            description=desc,
            frequency="event",
        )
        for f, desc in _SEC_FIELDS
    ]


def _provider_candidates() -> list[FeatureCandidate]:
    """Walk registered fetchers for any extra domain/field pairs."""
    out: list[FeatureCandidate] = []
    try:
        from aqp.providers.catalog import fetcher_catalog

        for domain, fetchers in fetcher_catalog().describe().items():
            for f in fetchers:
                vendor = (f.get("vendor_key") or "openbb").lower()
                fields = f.get("fields") or []
                if isinstance(fields, dict):
                    fields = [{"name": k, "description": v} for k, v in fields.items()]
                for fld in fields:
                    if not isinstance(fld, dict):
                        continue
                    name = fld.get("name") or fld.get("id") or ""
                    if not name:
                        continue
                    out.append(
                        FeatureCandidate(
                            id=f"{vendor}.{domain}.{name}",
                            source=vendor,
                            domain=domain,
                            field=str(name),
                            description=str(fld.get("description") or ""),
                        )
                    )
    except Exception:  # noqa: BLE001 - catalog walks are best-effort
        logger.debug("provider catalog walk failed", exc_info=True)
    return out


def all_candidates() -> list[FeatureCandidate]:
    out: list[FeatureCandidate] = []
    out.extend(_av_candidates())
    out.extend(_fred_candidates())
    out.extend(_gdelt_candidates())
    out.extend(_sec_candidates())
    out.extend(_provider_candidates())
    seen: set[str] = set()
    deduped: list[FeatureCandidate] = []
    for c in out:
        if c.id in seen:
            continue
        seen.add(c.id)
        deduped.append(c)
    return deduped


def to_dicts(candidates: list[FeatureCandidate]) -> list[dict[str, Any]]:
    return [asdict(c) for c in candidates]


def filter_candidates(
    candidates: list[FeatureCandidate],
    *,
    source: str | None = None,
    domain: str | None = None,
    query: str | None = None,
) -> list[FeatureCandidate]:
    out: list[FeatureCandidate] = []
    q = (query or "").strip().lower()
    for c in candidates:
        if source and c.source != source:
            continue
        if domain and c.domain != domain:
            continue
        if q and q not in (
            f"{c.source} {c.domain} {c.field} {c.description}".lower()
        ):
            continue
        out.append(c)
    return out


__all__ = [
    "FeatureCandidate",
    "all_candidates",
    "to_dicts",
    "filter_candidates",
]
