"""Curated port of OpenBB Platform standard_models.

Each file in this package hosts the paired ``QueryParams`` + ``Data``
classes for one or more related research endpoints. Where possible, the
``Data`` subclass extends the matching primitive in
:mod:`aqp.core.domain` so the platform's canonical schema and the
wire-format schema are the *same type*.

The catalog is grouped by functional family for discoverability:

- ``equity`` — EquityInfo, EquityHistorical, EquityQuote, EquityNbbo,
  EquitySearch, EquityScreener, EquityPeers.
- ``etf`` — EtfInfo, EtfHistorical, EtfHistoricalNav, EtfHoldings,
  EtfSectors, EtfCountries, EtfSearch.
- ``index`` — IndexInfo, IndexHistorical, IndexConstituents, IndexSearch,
  IndexSectors.
- ``fx`` — CurrencyPairs, CurrencyHistorical, CurrencyReferenceRates.
- ``crypto`` — CryptoHistorical, CryptoSearch.
- ``futures`` — FuturesInfo, FuturesCurve, FuturesHistorical,
  FuturesInstruments.
- ``bonds`` — BondReference, BondPrices, BondTrades, BondIndices.
- ``options`` — OptionsChains, OptionsSnapshots, OptionsUnusual.
- ``fundamentals`` — BalanceSheet, IncomeStatement, CashFlow (+ growth
  variants), FinancialRatios, KeyMetrics, HistoricalDividends,
  HistoricalSplits, HistoricalEps, HistoricalMarketCap,
  EarningsCallTranscript, ManagementDiscussionAnalysis,
  RevenueBusinessLine, RevenueGeographic, ReportedFinancials.
- ``estimates`` — AnalystEstimates, PriceTarget, PriceTargetConsensus,
  Forward{Eps, Ebitda, Pe, Sales}Estimates.
- ``calendar`` — CalendarEarnings, CalendarDividend, CalendarSplits,
  CalendarIpo, EconomicCalendar.
- ``ownership`` — InsiderTrading, InstitutionalOwnership, Form13FHR,
  KeyExecutives, ExecutiveCompensation, EquityPeers, EquityOwnership,
  EquityShortInterest, ShortVolume, EquityFtd, GovernmentTrades,
  TopRetail.
- ``news`` — CompanyNews, WorldNews.
- ``macro`` — TreasuryRates, TreasuryAuctions, TreasuryPrices,
  YieldCurve, FederalFundsRate, ConsumerPriceIndex, Unemployment,
  NonFarmPayrolls, GdpReal, GdpNominal, MoneyMeasures, FredSeries, Cot,
  BlsSeries.
- ``esg`` — EsgScore, EsgRiskRating, SectorPerformance.

Each ``*Data`` subclass gets ``populate_by_name`` + ``extra='allow'`` via
:class:`aqp.providers.base.Data`, so provider-specific fields arrive
unchanged and downstream consumers can access them via ``getattr`` or
``model_dump()``.
"""
