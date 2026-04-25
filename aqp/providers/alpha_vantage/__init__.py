"""Alpha Vantage provider fetchers."""
from __future__ import annotations

from typing import Any

from aqp.data.sources.alpha_vantage import AlphaVantageClient
from aqp.providers.base import CostTier, Fetcher
from aqp.providers.catalog import register_fetcher
from aqp.providers.standard_models.crypto import CryptoHistoricalData, CryptoHistoricalQueryParams
from aqp.providers.standard_models.equity import (
    EquityHistoricalData,
    EquityHistoricalQueryParams,
    EquityInfoData,
    EquityInfoQueryParams,
    EquityQuoteData,
    EquityQuoteQueryParams,
)
from aqp.providers.standard_models.fundamentals import (
    BalanceSheetData,
    BalanceSheetQueryParams,
    CashFlowData,
    CashFlowQueryParams,
    IncomeStatementData,
    IncomeStatementQueryParams,
)
from aqp.providers.standard_models.fx import CurrencyHistoricalData, CurrencyHistoricalQueryParams
from aqp.providers.standard_models.news import CompanyNewsData, CompanyNewsQueryParams
from aqp.providers.standard_models.options import OptionsChainsData, OptionsChainsQueryParams


def _client(credentials: dict[str, str] | None = None) -> AlphaVantageClient:
    return AlphaVantageClient(api_key=(credentials or {}).get("api_key"))


def _float(value: Any) -> float | None:
    if value in (None, "", "None", "null", "N/A", "-"):
        return None
    try:
        return float(str(value).rstrip("%"))
    except Exception:
        return None


def _bars(payload: Any, *, date_key: str = "date") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in getattr(payload, "bars", []) or []:
        row = bar if isinstance(bar, dict) else dict(bar)
        rows.append(
            {
                date_key: row.get("timestamp"),
                "open": _float(row.get("open")),
                "high": _float(row.get("high")),
                "low": _float(row.get("low")),
                "close": _float(row.get("close")),
                "volume": _float(row.get("volume")),
                "adj_close": _float(row.get("adjusted_close")),
            },
        )
    return rows


class _AlphaVantageFetcher:
    vendor_key = "alpha_vantage"
    rate_limit_key = "alpha_vantage"
    cost_tier = CostTier.FREEMIUM
    require_credentials = True


@register_fetcher("equity.info", priority=20)
class AlphaVantageEquityInfoFetcher(_AlphaVantageFetcher, Fetcher[EquityInfoQueryParams, list[EquityInfoData]]):
    description = "Alpha Vantage OVERVIEW company profile."

    @staticmethod
    def transform_query(params: dict[str, Any]) -> EquityInfoQueryParams:
        return EquityInfoQueryParams(**params)

    @staticmethod
    def extract_data(query: EquityInfoQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).fundamentals.overview(query.symbol).model_dump()

    @staticmethod
    def transform_data(query: EquityInfoQueryParams, data: dict[str, Any], **_: Any) -> list[EquityInfoData]:
        return [
            EquityInfoData(
                symbol=data.get("symbol") or query.symbol,
                name=data.get("name"),
                cik=data.get("cik"),
                stock_exchange=data.get("exchange"),
                sic=int(data["sic"]) if str(data.get("sic") or "").isdigit() else None,
                short_description=data.get("description"),
                company_url=data.get("official_site"),
                sector=data.get("sector"),
                industry_category=data.get("industry"),
            ),
        ]


@register_fetcher("equity.quote", priority=20)
class AlphaVantageEquityQuoteFetcher(_AlphaVantageFetcher, Fetcher[EquityQuoteQueryParams, list[EquityQuoteData]]):
    description = "Alpha Vantage GLOBAL_QUOTE snapshot."

    @staticmethod
    def transform_query(params: dict[str, Any]) -> EquityQuoteQueryParams:
        return EquityQuoteQueryParams(**params)

    @staticmethod
    def extract_data(query: EquityQuoteQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).timeseries.global_quote(query.symbol).model_dump()

    @staticmethod
    def transform_data(query: EquityQuoteQueryParams, data: dict[str, Any], **_: Any) -> list[EquityQuoteData]:
        return [
            EquityQuoteData(
                symbol=data.get("symbol") or query.symbol,
                last_price=_float(data.get("price")),
                open=_float(data.get("open")),
                high=_float(data.get("high")),
                low=_float(data.get("low")),
                prev_close=_float(data.get("previous_close")),
                change=_float(data.get("change")),
                change_percent=_float(data.get("change_percent")),
                volume=_float(data.get("volume")),
            ),
        ]


@register_fetcher("equity.historical", priority=20)
class AlphaVantageEquityHistoricalFetcher(_AlphaVantageFetcher, Fetcher[EquityHistoricalQueryParams, list[EquityHistoricalData]]):
    description = "Alpha Vantage daily/intraday historical OHLCV."

    @staticmethod
    def transform_query(params: dict[str, Any]) -> EquityHistoricalQueryParams:
        return EquityHistoricalQueryParams(**params)

    @staticmethod
    def extract_data(query: EquityHistoricalQueryParams, credentials: dict[str, str] | None) -> Any:
        client = _client(credentials)
        interval = str(query.interval or "1d")
        if interval.endswith("m") or interval.endswith("min"):
            return client.timeseries.intraday(query.symbol, interval=interval.replace("m", "min"))
        return client.timeseries.daily_adjusted(query.symbol, outputsize="full")

    @staticmethod
    def transform_data(query: EquityHistoricalQueryParams, data: Any, **_: Any) -> list[EquityHistoricalData]:
        return [EquityHistoricalData(**row) for row in _bars(data)]


def _statement_rows(data: dict[str, Any], period: str | None, limit: int | None) -> list[dict[str, Any]]:
    key = "quarterly" if str(period or "").startswith("q") else "annual"
    rows = list(data.get(key) or [])
    if limit:
        rows = rows[: int(limit)]
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = row.model_dump() if hasattr(row, "model_dump") else dict(row)
        payload["symbol"] = data.get("symbol")
        payload.setdefault("period", period or "annual")
        out.append(payload)
    return out


@register_fetcher("fundamentals.income_statement", priority=20)
class AlphaVantageIncomeStatementFetcher(_AlphaVantageFetcher, Fetcher[IncomeStatementQueryParams, list[IncomeStatementData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> IncomeStatementQueryParams:
        return IncomeStatementQueryParams(**params)

    @staticmethod
    def extract_data(query: IncomeStatementQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).fundamentals.income_statement(query.symbol)

    @staticmethod
    def transform_data(query: IncomeStatementQueryParams, data: dict[str, Any], **_: Any) -> list[IncomeStatementData]:
        return [IncomeStatementData.model_validate(row) for row in _statement_rows(data, query.period, query.limit)]


@register_fetcher("fundamentals.balance_sheet", priority=20)
class AlphaVantageBalanceSheetFetcher(_AlphaVantageFetcher, Fetcher[BalanceSheetQueryParams, list[BalanceSheetData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> BalanceSheetQueryParams:
        return BalanceSheetQueryParams(**params)

    @staticmethod
    def extract_data(query: BalanceSheetQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).fundamentals.balance_sheet(query.symbol)

    @staticmethod
    def transform_data(query: BalanceSheetQueryParams, data: dict[str, Any], **_: Any) -> list[BalanceSheetData]:
        return [BalanceSheetData.model_validate(row) for row in _statement_rows(data, query.period, query.limit)]


@register_fetcher("fundamentals.cash_flow", priority=20)
class AlphaVantageCashFlowFetcher(_AlphaVantageFetcher, Fetcher[CashFlowQueryParams, list[CashFlowData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> CashFlowQueryParams:
        return CashFlowQueryParams(**params)

    @staticmethod
    def extract_data(query: CashFlowQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).fundamentals.cash_flow(query.symbol)

    @staticmethod
    def transform_data(query: CashFlowQueryParams, data: dict[str, Any], **_: Any) -> list[CashFlowData]:
        return [CashFlowData.model_validate(row) for row in _statement_rows(data, query.period, query.limit)]


@register_fetcher("news.company", priority=20)
class AlphaVantageCompanyNewsFetcher(_AlphaVantageFetcher, Fetcher[CompanyNewsQueryParams, list[CompanyNewsData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> CompanyNewsQueryParams:
        return CompanyNewsQueryParams(**params)

    @staticmethod
    def extract_data(query: CompanyNewsQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials).intelligence.news(tickers=query.symbols, limit=query.limit).model_dump()

    @staticmethod
    def transform_data(query: CompanyNewsQueryParams, data: dict[str, Any], **_: Any) -> list[CompanyNewsData]:
        return [CompanyNewsData.model_validate(row) for row in data.get("feed", [])]


@register_fetcher("options.chains", priority=20)
class AlphaVantageOptionsChainsFetcher(_AlphaVantageFetcher, Fetcher[OptionsChainsQueryParams, list[OptionsChainsData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> OptionsChainsQueryParams:
        return OptionsChainsQueryParams(**params)

    @staticmethod
    def extract_data(query: OptionsChainsQueryParams, credentials: dict[str, str] | None) -> dict[str, Any]:
        return _client(credentials)._json(function="HISTORICAL_OPTIONS", symbol=query.symbol)

    @staticmethod
    def transform_data(query: OptionsChainsQueryParams, data: dict[str, Any], **_: Any) -> list[OptionsChainsData]:
        return [OptionsChainsData.model_validate(row) for row in data.get("data", [])]


@register_fetcher("fx.historical", priority=20)
class AlphaVantageFxHistoricalFetcher(_AlphaVantageFetcher, Fetcher[CurrencyHistoricalQueryParams, list[CurrencyHistoricalData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> CurrencyHistoricalQueryParams:
        return CurrencyHistoricalQueryParams(**params)

    @staticmethod
    def extract_data(query: CurrencyHistoricalQueryParams, credentials: dict[str, str] | None) -> Any:
        base, _, quote = query.symbol.replace("/", "").partition("-")
        if not quote and len(base) >= 6:
            base, quote = base[:3], base[3:6]
        return _client(credentials).forex.daily(from_symbol=base, to_symbol=quote or "USD")

    @staticmethod
    def transform_data(query: CurrencyHistoricalQueryParams, data: Any, **_: Any) -> list[CurrencyHistoricalData]:
        return [CurrencyHistoricalData(**row) for row in _bars(data)]


@register_fetcher("crypto.historical", priority=20)
class AlphaVantageCryptoHistoricalFetcher(_AlphaVantageFetcher, Fetcher[CryptoHistoricalQueryParams, list[CryptoHistoricalData]]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> CryptoHistoricalQueryParams:
        return CryptoHistoricalQueryParams(**params)

    @staticmethod
    def extract_data(query: CryptoHistoricalQueryParams, credentials: dict[str, str] | None) -> Any:
        return _client(credentials).crypto.daily(query.symbol, "USD")

    @staticmethod
    def transform_data(query: CryptoHistoricalQueryParams, data: Any, **_: Any) -> list[CryptoHistoricalData]:
        return [CryptoHistoricalData(**row) for row in _bars(data)]


__all__ = [
    "AlphaVantageBalanceSheetFetcher",
    "AlphaVantageCashFlowFetcher",
    "AlphaVantageCompanyNewsFetcher",
    "AlphaVantageCryptoHistoricalFetcher",
    "AlphaVantageEquityHistoricalFetcher",
    "AlphaVantageEquityInfoFetcher",
    "AlphaVantageEquityQuoteFetcher",
    "AlphaVantageFxHistoricalFetcher",
    "AlphaVantageIncomeStatementFetcher",
    "AlphaVantageOptionsChainsFetcher",
]
