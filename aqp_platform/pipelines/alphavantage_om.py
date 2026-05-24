"""Redis OM models for Alpha Vantage-sourced entities.

Covers fundamentals (company overview, ETF profile, insider txns, earnings
reports/transcripts), universe data (listing status, IPO calendar), and news
articles. Models use the global ``rpi`` key prefix and an ``av:`` model prefix
so Redis Stack keeps them isolated from the document store.

Same stubbing pattern as :mod:`pipelines.redis_om_models`: importable even when
``redis-om`` is not installed.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_OM_AVAILABLE = True
try:  # pragma: no cover - optional dependency
    from redis_om import Field, JsonModel, Migrator
except Exception as exc:  # pragma: no cover
    _OM_AVAILABLE = False
    Field = None  # type: ignore
    JsonModel = None  # type: ignore
    Migrator = None  # type: ignore
    logger.info("redis-om not installed; AV model classes will be stubs (%s)", exc)


if _OM_AVAILABLE:

    class AVCompanyOverview(JsonModel):  # type: ignore[misc]
        """Full OVERVIEW snapshot, indexed by symbol/sector/industry."""

        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        name: str = Field(index=True, full_text_search=True, default="")
        description: str = Field(default="", full_text_search=True)
        asset_type: str = Field(index=True, default="")
        exchange: str = Field(index=True, default="")
        currency: str = Field(index=True, default="")
        country: str = Field(index=True, default="")
        sector: str = Field(index=True, default="")
        industry: str = Field(index=True, default="")
        cik: str = Field(index=True, default="")
        market_cap: str = Field(default="")
        pe_ratio: str = Field(default="")
        eps: str = Field(default="")
        beta: str = Field(default="")
        dividend_yield: str = Field(default="")
        shares_outstanding: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        raw: dict = Field(default_factory=dict)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:overview"

    class AVEtfProfile(JsonModel):  # type: ignore[misc]
        """ETF_PROFILE holdings and sectors."""

        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        net_assets: str = Field(default="")
        net_expense_ratio: str = Field(default="")
        dividend_yield: str = Field(default="")
        inception_date: str = Field(default="")
        leveraged: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        holdings: list[dict] = Field(default_factory=list)
        sectors: list[dict] = Field(default_factory=list)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:etf"

    class AVIncomeStatement(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        fiscal_date_ending: str = Field(index=True)
        period: str = Field(index=True, default="annual")  # annual|quarterly
        reported_currency: str = Field(default="")
        total_revenue: str = Field(default="")
        gross_profit: str = Field(default="")
        operating_income: str = Field(default="")
        net_income: str = Field(default="")
        ebitda: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        raw: dict = Field(default_factory=dict)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:income"

    class AVBalanceSheet(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        fiscal_date_ending: str = Field(index=True)
        period: str = Field(index=True, default="annual")
        reported_currency: str = Field(default="")
        total_assets: str = Field(default="")
        total_liabilities: str = Field(default="")
        total_shareholder_equity: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        raw: dict = Field(default_factory=dict)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:balance"

    class AVCashFlow(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        fiscal_date_ending: str = Field(index=True)
        period: str = Field(index=True, default="annual")
        reported_currency: str = Field(default="")
        operating_cashflow: str = Field(default="")
        cashflow_from_investment: str = Field(default="")
        cashflow_from_financing: str = Field(default="")
        capital_expenditures: str = Field(default="")
        net_income: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        raw: dict = Field(default_factory=dict)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:cashflow"

    class AVEarningsReport(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        fiscal_date_ending: str = Field(index=True)
        period: str = Field(index=True, default="annual")
        reported_date: str = Field(default="")
        reported_eps: str = Field(default="")
        estimated_eps: str = Field(default="")
        surprise: str = Field(default="")
        surprise_percentage: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:earnings"

    class AVInsiderTransaction(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        ticker: str = Field(index=True)
        executive: str = Field(index=True, full_text_search=True, default="")
        transaction_date: str = Field(index=True, default="")
        security_type: str = Field(index=True, default="")
        acquisition_or_disposal: str = Field(index=True, default="")
        shares: str = Field(default="")
        share_price: str = Field(default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:insider"

    class AVNewsArticle(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        article_id: str = Field(index=True)
        url: str = Field(index=True)
        title: str = Field(index=True, full_text_search=True, default="")
        summary: str = Field(default="", full_text_search=True)
        source: str = Field(index=True, default="")
        source_domain: str = Field(index=True, default="")
        time_published: str = Field(index=True, default="")
        tickers: list[str] = Field(index=True, default_factory=list)
        topics: list[str] = Field(index=True, default_factory=list)
        overall_sentiment_score: float = Field(index=True, sortable=True, default=0.0)
        overall_sentiment_label: str = Field(index=True, default="")
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)
        raw: dict = Field(default_factory=dict)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:news"

    class AVEarningsTranscript(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        quarter: str = Field(index=True)
        turn_count: int = Field(index=True, sortable=True, default=0)
        avg_sentiment: float = Field(index=True, sortable=True, default=0.0)
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)
        transcript: list[dict] = Field(default_factory=list)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:transcript"

    class AVListingStatus(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        name: str = Field(index=True, full_text_search=True, default="")
        exchange: str = Field(index=True, default="")
        asset_type: str = Field(index=True, default="")
        ipo_date: str = Field(index=True, default="")
        delisting_date: str = Field(index=True, default="")
        status: str = Field(index=True, default="active")
        as_of: str = Field(index=True, default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:listing"

    class AVIpoEntry(JsonModel):  # type: ignore[misc]
        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        symbol: str = Field(index=True)
        name: str = Field(index=True, default="")
        ipo_date: str = Field(index=True, default="")
        price_range_low: str = Field(default="")
        price_range_high: str = Field(default="")
        currency: str = Field(default="")
        exchange: str = Field(index=True, default="")
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "av:ipo"

    def ensure_av_migrated() -> None:
        """Create / refresh RediSearch indexes for the AV model family."""

        try:
            Migrator().run()
        except Exception as exc:  # pragma: no cover
            logger.warning("AV redis-om migration failed: %s", exc)

    _OM_MODELS = [
        AVCompanyOverview,
        AVEtfProfile,
        AVIncomeStatement,
        AVBalanceSheet,
        AVCashFlow,
        AVEarningsReport,
        AVInsiderTransaction,
        AVNewsArticle,
        AVEarningsTranscript,
        AVListingStatus,
        AVIpoEntry,
    ]

else:  # pragma: no cover

    class _OMStub:
        _NOT_INSTALLED_MSG = (
            "redis-om is not installed. Install redis-om to use the AV OM models."
        )

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(self._NOT_INSTALLED_MSG)

        @classmethod
        def find(cls, *_, **__) -> Any:
            raise RuntimeError(cls._NOT_INSTALLED_MSG)

        @classmethod
        def get(cls, *_, **__) -> Any:
            raise RuntimeError(cls._NOT_INSTALLED_MSG)

    class AVCompanyOverview(_OMStub): ...  # type: ignore[misc]
    class AVEtfProfile(_OMStub): ...  # type: ignore[misc]
    class AVIncomeStatement(_OMStub): ...  # type: ignore[misc]
    class AVBalanceSheet(_OMStub): ...  # type: ignore[misc]
    class AVCashFlow(_OMStub): ...  # type: ignore[misc]
    class AVEarningsReport(_OMStub): ...  # type: ignore[misc]
    class AVInsiderTransaction(_OMStub): ...  # type: ignore[misc]
    class AVNewsArticle(_OMStub): ...  # type: ignore[misc]
    class AVEarningsTranscript(_OMStub): ...  # type: ignore[misc]
    class AVListingStatus(_OMStub): ...  # type: ignore[misc]
    class AVIpoEntry(_OMStub): ...  # type: ignore[misc]

    def ensure_av_migrated() -> None:
        logger.info("redis-om not installed; ensure_av_migrated is a no-op")

    _OM_MODELS = []


__all__ = [
    "AVBalanceSheet",
    "AVCashFlow",
    "AVCompanyOverview",
    "AVEarningsReport",
    "AVEarningsTranscript",
    "AVEtfProfile",
    "AVIncomeStatement",
    "AVInsiderTransaction",
    "AVIpoEntry",
    "AVListingStatus",
    "AVNewsArticle",
    "ensure_av_migrated",
]
