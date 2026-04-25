"""Execution Ledger, domain tables, and session persistence.

Submodules:

- :mod:`aqp.persistence.models` — original ledger + dataset + ml-plan tables
  plus the polymorphic ``Instrument`` parent.
- :mod:`aqp.persistence.models_instruments` — joined-table subclasses
  (``InstrumentEquity``, ``InstrumentOption``, ``InstrumentFuture``…).
- :mod:`aqp.persistence.models_entities` — issuer / entity graph
  (``Issuer``, ``Sector``, ``Industry``, ``EntityRelationship``,
  ``KeyExecutive``, ``ExecutiveCompensation``, ``Location``…).
- :mod:`aqp.persistence.models_fundamentals` — financial statements,
  ratios, metrics, historicals, transcripts.
- :mod:`aqp.persistence.models_events` — corporate / calendar / analyst /
  regulatory / ESG event tables.
- :mod:`aqp.persistence.models_ownership` — insider / institutional /
  13F / short interest / float / politician trades / fund holdings.
- :mod:`aqp.persistence.models_news` — news items + entity M2M +
  sentiment.
- :mod:`aqp.persistence.models_macro` — economic series +
  observations + CoT + BLS + treasury/yield-curve + options/futures
  snapshots + market microstructure.
- :mod:`aqp.persistence.models_taxonomy` — taxonomy schemes + nodes +
  polymorphic entity tags + entity crosswalk.

Importing this package triggers SQLAlchemy registration for every table
so ``Base.metadata`` and Alembic's autogenerate pick them up.
"""

from aqp.persistence.db import (
    AsyncSessionLocal,
    SessionLocal,
    async_engine,
    async_session_dep,
    engine,
    get_async_session,
    get_session,
)
from aqp.persistence.ledger import LedgerWriter
from aqp.persistence.models import (
    AgentRun,
    BacktestRun,
    Base,
    ChatMessage,
    DataLink,
    DataSource,
    DatasetCatalog,
    DatasetVersion,
    ExperimentPlan,
    Fill,
    FredSeries,
    GDeltMention,
    IdentifierLink,
    Instrument,
    LedgerEntry,
    ModelDeployment,
    ModelVersion,
    OrderRecord,
    PipelineRecipe,
    RLEpisode,
    SecFiling,
    Session,
    SignalEntry,
    SplitArtifact,
    SplitPlan,
    Strategy,
)
from aqp.persistence.models_entities import (
    EntityRelationship,
    ExecutiveCompensation,
    Fund,
    GovernmentEntity,
    Industry,
    IndustryClassification,
    Issuer,
    KeyExecutive,
    Location,
    Sector,
)
from aqp.persistence.models_events import (
    AnalystEstimate,
    CalendarEventRow,
    CorporateEvent,
    DividendEventRow,
    EarningsEventRow,
    EsgEventRow,
    ForwardEstimate,
    IpoEventRow,
    MergerEventRow,
    PriceTarget,
    RegulatoryEventRow,
    SplitEventRow,
)
from aqp.persistence.models_fundamentals import (
    EarningsCallTranscript,
    FinancialRatios,
    FinancialStatement,
    HistoricalMarketCap,
    KeyMetrics,
    ManagementDiscussionAnalysis,
    ReportedFinancials,
    RevenueBreakdown,
)
from aqp.persistence.models_instruments import (
    InstrumentBetting,
    InstrumentBond,
    InstrumentCfd,
    InstrumentCommodity,
    InstrumentCrypto,
    InstrumentETF,
    InstrumentEquity,
    InstrumentFuture,
    InstrumentFxPair,
    InstrumentIndex,
    InstrumentOption,
    InstrumentSynthetic,
    InstrumentTokenizedAsset,
)
from aqp.persistence.models_macro import (
    BlsSeriesRow,
    CotReportRow,
    EconomicObservation,
    EconomicSeriesRow,
    FuturesCurveRow,
    MarketHolidayRow,
    MarketStatusHistory,
    OptionChainSnapshot,
    OptionSeries,
    TreasuryRateRow,
    YieldCurveRow,
)
from aqp.persistence.models_news import NewsItemEntity, NewsItemRow, NewsSentiment
from aqp.persistence.models_ownership import (
    Form13FHoldingRow,
    FundHolding,
    InsiderTransactionRow,
    InstitutionalHoldingRow,
    PoliticianTrade,
    SharesFloatSnapshot,
    ShortInterestSnapshot,
)
from aqp.persistence.models_taxonomy import (
    EntityCrosswalk,
    EntityTag,
    TaxonomyNode,
    TaxonomyScheme,
)

__all__ = [
    # Original core
    "AgentRun",
    "AsyncSessionLocal",
    "BacktestRun",
    "Base",
    "ChatMessage",
    "DataLink",
    "DataSource",
    "DatasetCatalog",
    "DatasetVersion",
    "ExperimentPlan",
    "Fill",
    "FredSeries",
    "GDeltMention",
    "IdentifierLink",
    "Instrument",
    "LedgerEntry",
    "LedgerWriter",
    "ModelDeployment",
    "ModelVersion",
    "OrderRecord",
    "PipelineRecipe",
    "RLEpisode",
    "SecFiling",
    "Session",
    "SessionLocal",
    "SignalEntry",
    "SplitArtifact",
    "SplitPlan",
    "Strategy",
    # Polymorphic instruments
    "InstrumentBetting",
    "InstrumentBond",
    "InstrumentCfd",
    "InstrumentCommodity",
    "InstrumentCrypto",
    "InstrumentETF",
    "InstrumentEquity",
    "InstrumentFuture",
    "InstrumentFxPair",
    "InstrumentIndex",
    "InstrumentOption",
    "InstrumentSynthetic",
    "InstrumentTokenizedAsset",
    # Entity graph
    "EntityRelationship",
    "ExecutiveCompensation",
    "Fund",
    "GovernmentEntity",
    "Industry",
    "IndustryClassification",
    "Issuer",
    "KeyExecutive",
    "Location",
    "Sector",
    # Fundamentals
    "EarningsCallTranscript",
    "FinancialRatios",
    "FinancialStatement",
    "HistoricalMarketCap",
    "KeyMetrics",
    "ManagementDiscussionAnalysis",
    "ReportedFinancials",
    "RevenueBreakdown",
    # Events / calendar
    "AnalystEstimate",
    "CalendarEventRow",
    "CorporateEvent",
    "DividendEventRow",
    "EarningsEventRow",
    "EsgEventRow",
    "ForwardEstimate",
    "IpoEventRow",
    "MergerEventRow",
    "PriceTarget",
    "RegulatoryEventRow",
    "SplitEventRow",
    # Ownership
    "Form13FHoldingRow",
    "FundHolding",
    "InsiderTransactionRow",
    "InstitutionalHoldingRow",
    "PoliticianTrade",
    "SharesFloatSnapshot",
    "ShortInterestSnapshot",
    # News
    "NewsItemEntity",
    "NewsItemRow",
    "NewsSentiment",
    # Macro / microstructure
    "BlsSeriesRow",
    "CotReportRow",
    "EconomicObservation",
    "EconomicSeriesRow",
    "FuturesCurveRow",
    "MarketHolidayRow",
    "MarketStatusHistory",
    "OptionChainSnapshot",
    "OptionSeries",
    "TreasuryRateRow",
    "YieldCurveRow",
    # Taxonomy
    "EntityCrosswalk",
    "EntityTag",
    "TaxonomyNode",
    "TaxonomyScheme",
    # DB utilities
    "async_engine",
    "async_session_dep",
    "engine",
    "get_async_session",
    "get_session",
]
