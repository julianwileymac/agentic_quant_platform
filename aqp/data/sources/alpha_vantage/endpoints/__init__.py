"""Alpha Vantage endpoint-group facades."""
from __future__ import annotations

from typing import Any, Iterable

from aqp.data.sources.alpha_vantage._parsers import normalize_mapping
from aqp.data.sources.alpha_vantage.endpoints._base import BaseEndpoint, _prune
from aqp.data.sources.alpha_vantage.models import (
    AVModel,
    GlobalQuote,
    MarketStatusPayload,
    SymbolSearchMatch,
)


class TimeSeries(BaseEndpoint):
    def intraday(self, symbol: str, *, interval: str = "5min", outputsize: str | None = None, **extra: Any):
        return self._time_series(self._sync_request(_prune({"function": "TIME_SERIES_INTRADAY", "symbol": symbol, "interval": interval, "outputsize": outputsize, **extra})))

    async def aintraday(self, symbol: str, *, interval: str = "5min", outputsize: str | None = None, **extra: Any):
        return self._time_series(await self._async_request(_prune({"function": "TIME_SERIES_INTRADAY", "symbol": symbol, "interval": interval, "outputsize": outputsize, **extra})))

    def daily(self, symbol: str, *, outputsize: str | None = None, **extra: Any):
        return self._time_series(self._sync_request(_prune({"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": outputsize, **extra})))

    async def adaily(self, symbol: str, *, outputsize: str | None = None, **extra: Any):
        return self._time_series(await self._async_request(_prune({"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": outputsize, **extra})))

    def daily_adjusted(self, symbol: str, *, outputsize: str | None = None, **extra: Any):
        return self._time_series(self._sync_request(_prune({"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": symbol, "outputsize": outputsize, **extra})))

    async def adaily_adjusted(self, symbol: str, *, outputsize: str | None = None, **extra: Any):
        return self._time_series(await self._async_request(_prune({"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": symbol, "outputsize": outputsize, **extra})))

    def weekly(self, symbol: str):
        return self._time_series(self._sync_request({"function": "TIME_SERIES_WEEKLY", "symbol": symbol}))

    async def aweekly(self, symbol: str):
        return self._time_series(await self._async_request({"function": "TIME_SERIES_WEEKLY", "symbol": symbol}))

    def weekly_adjusted(self, symbol: str):
        return self._time_series(self._sync_request({"function": "TIME_SERIES_WEEKLY_ADJUSTED", "symbol": symbol}))

    async def aweekly_adjusted(self, symbol: str):
        return self._time_series(await self._async_request({"function": "TIME_SERIES_WEEKLY_ADJUSTED", "symbol": symbol}))

    def monthly(self, symbol: str):
        return self._time_series(self._sync_request({"function": "TIME_SERIES_MONTHLY", "symbol": symbol}))

    async def amonthly(self, symbol: str):
        return self._time_series(await self._async_request({"function": "TIME_SERIES_MONTHLY", "symbol": symbol}))

    def monthly_adjusted(self, symbol: str):
        return self._time_series(self._sync_request({"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol}))

    async def amonthly_adjusted(self, symbol: str):
        return self._time_series(await self._async_request({"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol}))

    def global_quote(self, symbol: str, **extra: Any) -> GlobalQuote:
        payload = self._sync_request(_prune({"function": "GLOBAL_QUOTE", "symbol": symbol, **extra}))
        return GlobalQuote.model_validate(payload.get("Global Quote", payload))

    async def aglobal_quote(self, symbol: str, **extra: Any) -> GlobalQuote:
        payload = await self._async_request(_prune({"function": "GLOBAL_QUOTE", "symbol": symbol, **extra}))
        return GlobalQuote.model_validate(payload.get("Global Quote", payload))

    def search(self, keywords: str) -> list[SymbolSearchMatch]:
        payload = self._sync_request({"function": "SYMBOL_SEARCH", "keywords": keywords})
        return [SymbolSearchMatch.model_validate(row) for row in payload.get("bestMatches", [])]

    async def asearch(self, keywords: str) -> list[SymbolSearchMatch]:
        payload = await self._async_request({"function": "SYMBOL_SEARCH", "keywords": keywords})
        return [SymbolSearchMatch.model_validate(row) for row in payload.get("bestMatches", [])]

    def market_status(self) -> MarketStatusPayload:
        payload = self._sync_request({"function": "MARKET_STATUS"})
        return MarketStatusPayload(markets=[normalize_mapping(row) for row in payload.get("markets", [])])

    async def amarket_status(self) -> MarketStatusPayload:
        payload = await self._async_request({"function": "MARKET_STATUS"})
        return MarketStatusPayload(markets=[normalize_mapping(row) for row in payload.get("markets", [])])

    async def arealtime_bulk_quotes(self, symbols: Iterable[str], **extra: Any) -> list[dict[str, Any]]:
        payload = await self._async_request(
            _prune({"function": "REALTIME_BULK_QUOTES", "symbol": ",".join(symbols), **extra})
        )
        return payload.get("data", payload if isinstance(payload, list) else [])


class Fundamentals(BaseEndpoint):
    def overview(self, symbol: str) -> AVModel:
        return self._model(self._sync_request({"function": "OVERVIEW", "symbol": symbol}))

    async def aoverview(self, symbol: str) -> AVModel:
        return self._model(await self._async_request({"function": "OVERVIEW", "symbol": symbol}))

    def etf_profile(self, symbol: str) -> AVModel:
        return self._model(self._sync_request({"function": "ETF_PROFILE", "symbol": symbol}))

    async def aetf_profile(self, symbol: str) -> AVModel:
        return self._model(await self._async_request({"function": "ETF_PROFILE", "symbol": symbol}))

    def _rows(self, function: str, symbol: str, key: str = "data") -> list[AVModel]:
        payload = self._sync_request({"function": function, "symbol": symbol})
        return [self._model(row) for row in payload.get(key, [])]

    async def _arows(self, function: str, symbol: str, key: str = "data") -> list[AVModel]:
        payload = await self._async_request({"function": function, "symbol": symbol})
        return [self._model(row) for row in payload.get(key, [])]

    def dividends(self, symbol: str):
        return self._rows("DIVIDENDS", symbol)

    async def adividends(self, symbol: str):
        return await self._arows("DIVIDENDS", symbol)

    def splits(self, symbol: str):
        return self._rows("SPLITS", symbol)

    async def asplits(self, symbol: str):
        return await self._arows("SPLITS", symbol)

    def earnings_estimates(self, symbol: str):
        return self._rows("EARNINGS_ESTIMATES", symbol, "estimates")

    async def aearnings_estimates(self, symbol: str):
        return await self._arows("EARNINGS_ESTIMATES", symbol, "estimates")

    def shares_outstanding(self, symbol: str):
        return self._rows("SHARES_OUTSTANDING", symbol)

    async def ashares_outstanding(self, symbol: str):
        return await self._arows("SHARES_OUTSTANDING", symbol)

    def _statement(self, function: str, symbol: str) -> dict[str, Any]:
        payload = self._sync_request({"function": function, "symbol": symbol})
        return {
            "symbol": payload.get("symbol") or symbol,
            "annual": [self._model(row) for row in payload.get("annualReports", [])],
            "quarterly": [self._model(row) for row in payload.get("quarterlyReports", [])],
        }

    async def _astatement(self, function: str, symbol: str) -> dict[str, Any]:
        payload = await self._async_request({"function": function, "symbol": symbol})
        return {
            "symbol": payload.get("symbol") or symbol,
            "annual": [self._model(row) for row in payload.get("annualReports", [])],
            "quarterly": [self._model(row) for row in payload.get("quarterlyReports", [])],
        }

    def income_statement(self, symbol: str):
        return self._statement("INCOME_STATEMENT", symbol)

    async def aincome_statement(self, symbol: str):
        return await self._astatement("INCOME_STATEMENT", symbol)

    def balance_sheet(self, symbol: str):
        return self._statement("BALANCE_SHEET", symbol)

    async def abalance_sheet(self, symbol: str):
        return await self._astatement("BALANCE_SHEET", symbol)

    def cash_flow(self, symbol: str):
        return self._statement("CASH_FLOW", symbol)

    async def acash_flow(self, symbol: str):
        return await self._astatement("CASH_FLOW", symbol)

    def earnings(self, symbol: str):
        payload = self._sync_request({"function": "EARNINGS", "symbol": symbol})
        return self._model(payload)

    async def aearnings(self, symbol: str):
        payload = await self._async_request({"function": "EARNINGS", "symbol": symbol})
        return self._model(payload)

    def earnings_calendar(self, *, symbol: str | None = None, horizon: str | None = None) -> str:
        return str(self._sync_request(_prune({"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": horizon}), datatype="csv"))

    async def aearnings_calendar(self, *, symbol: str | None = None, horizon: str | None = None) -> str:
        return str(await self._async_request(_prune({"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": horizon}), datatype="csv"))

    def ipo_calendar(self) -> str:
        return str(self._sync_request({"function": "IPO_CALENDAR"}, datatype="csv"))

    async def aipo_calendar(self) -> str:
        return str(await self._async_request({"function": "IPO_CALENDAR"}, datatype="csv"))

    def listing_status(self, *, date: str | None = None, state: str | None = None) -> str:
        return str(self._sync_request(_prune({"function": "LISTING_STATUS", "date": date, "state": state}), datatype="csv"))

    async def alisting_status(self, *, date: str | None = None, state: str | None = None) -> str:
        return str(await self._async_request(_prune({"function": "LISTING_STATUS", "date": date, "state": state}), datatype="csv"))


class Intelligence(BaseEndpoint):
    def news(self, **params: Any) -> AVModel:
        return self._model(self._sync_request(_prune({"function": "NEWS_SENTIMENT", **params})))

    async def anews(self, **params: Any) -> AVModel:
        return self._model(await self._async_request(_prune({"function": "NEWS_SENTIMENT", **params})))

    def top_movers(self, **params: Any) -> AVModel:
        return self._model(self._sync_request(_prune({"function": "TOP_GAINERS_LOSERS", **params})))

    async def atop_movers(self, **params: Any) -> AVModel:
        return self._model(await self._async_request(_prune({"function": "TOP_GAINERS_LOSERS", **params})))

    def earnings_transcript(self, symbol: str, quarter: str) -> AVModel:
        return self._model(self._sync_request({"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol, "quarter": quarter}))

    async def aearnings_transcript(self, symbol: str, quarter: str) -> AVModel:
        return self._model(await self._async_request({"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": symbol, "quarter": quarter}))

    def insider(self, symbol: str):
        payload = self._sync_request({"function": "INSIDER_TRANSACTIONS", "symbol": symbol})
        return [self._model(row) for row in payload.get("data", [])]

    async def ainsider(self, symbol: str):
        payload = await self._async_request({"function": "INSIDER_TRANSACTIONS", "symbol": symbol})
        return [self._model(row) for row in payload.get("data", [])]

    def institutional(self, symbol: str):
        payload = self._sync_request({"function": "INSTITUTIONAL_HOLDERS", "symbol": symbol})
        return [self._model(row) for row in payload.get("data", [])]

    async def ainstitutional(self, symbol: str):
        payload = await self._async_request({"function": "INSTITUTIONAL_HOLDERS", "symbol": symbol})
        return [self._model(row) for row in payload.get("data", [])]

    async def aanalytics_fixed(self, **params: Any):
        payload = await self._async_request(_prune({"function": "ANALYTICS_FIXED_WINDOW", **params}))
        return self._model(payload)

    async def aanalytics_sliding(self, **params: Any):
        payload = await self._async_request(_prune({"function": "ANALYTICS_SLIDING_WINDOW", **params}))
        return self._model(payload)


class Forex(BaseEndpoint):
    def exchange_rate(self, from_currency: str, to_currency: str):
        payload = self._sync_request(
            {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": from_currency, "to_currency": to_currency},
        )
        return self._model(payload.get("Realtime Currency Exchange Rate", {}))

    async def aexchange_rate(self, from_currency: str, to_currency: str):
        payload = await self._async_request(
            {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": from_currency, "to_currency": to_currency},
        )
        return self._model(payload.get("Realtime Currency Exchange Rate", {}))

    def intraday(self, **params: Any):
        return self._time_series(self._sync_request(_prune({"function": "FX_INTRADAY", **params})))

    async def aintraday(self, **params: Any):
        return self._time_series(await self._async_request(_prune({"function": "FX_INTRADAY", **params})))

    def daily(self, **params: Any):
        return self._time_series(self._sync_request(_prune({"function": "FX_DAILY", **params})))

    async def adaily(self, **params: Any):
        return self._time_series(await self._async_request(_prune({"function": "FX_DAILY", **params})))

    def weekly(self, **params: Any):
        return self._time_series(self._sync_request(_prune({"function": "FX_WEEKLY", **params})))

    async def aweekly(self, **params: Any):
        return self._time_series(await self._async_request(_prune({"function": "FX_WEEKLY", **params})))

    def monthly(self, **params: Any):
        return self._time_series(self._sync_request(_prune({"function": "FX_MONTHLY", **params})))

    async def amonthly(self, **params: Any):
        return self._time_series(await self._async_request(_prune({"function": "FX_MONTHLY", **params})))


class Crypto(BaseEndpoint):
    def exchange_rate(self, symbol: str, market: str):
        payload = self._sync_request(
            {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": symbol, "to_currency": market},
        )
        return self._model(payload.get("Realtime Currency Exchange Rate", {}))

    async def aexchange_rate(self, symbol: str, market: str):
        payload = await self._async_request(
            {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": symbol, "to_currency": market},
        )
        return self._model(payload.get("Realtime Currency Exchange Rate", {}))

    def intraday(self, **params: Any):
        return self._time_series(self._sync_request(_prune({"function": "CRYPTO_INTRADAY", **params})))

    async def aintraday(self, **params: Any):
        return self._time_series(await self._async_request(_prune({"function": "CRYPTO_INTRADAY", **params})))

    def daily(self, symbol: str, market: str = "USD"):
        return self._time_series(
            self._sync_request({"function": "DIGITAL_CURRENCY_DAILY", "symbol": symbol, "market": market}),
        )

    async def adaily(self, symbol: str, market: str = "USD"):
        return self._time_series(
            await self._async_request({"function": "DIGITAL_CURRENCY_DAILY", "symbol": symbol, "market": market}),
        )

    def weekly(self, symbol: str, market: str = "USD"):
        return self._time_series(
            self._sync_request({"function": "DIGITAL_CURRENCY_WEEKLY", "symbol": symbol, "market": market}),
        )

    async def aweekly(self, symbol: str, market: str = "USD"):
        return self._time_series(
            await self._async_request({"function": "DIGITAL_CURRENCY_WEEKLY", "symbol": symbol, "market": market}),
        )

    def monthly(self, symbol: str, market: str = "USD"):
        return self._time_series(
            self._sync_request({"function": "DIGITAL_CURRENCY_MONTHLY", "symbol": symbol, "market": market}),
        )

    async def amonthly(self, symbol: str, market: str = "USD"):
        return self._time_series(
            await self._async_request({"function": "DIGITAL_CURRENCY_MONTHLY", "symbol": symbol, "market": market}),
        )


class Options(BaseEndpoint):
    async def arealtime(self, symbol: str, contract: str | None = None):
        payload = await self._async_request(
            _prune({"function": "REALTIME_OPTIONS", "symbol": symbol, "contract": contract}),
        )
        return self._model(payload)

    async def ahistorical(self, symbol: str, date: str | None = None):
        payload = await self._async_request(
            _prune({"function": "HISTORICAL_OPTIONS", "symbol": symbol, "date": date}),
        )
        return self._model(payload)

    async def arealtime_put_call_ratio(self, symbol: str):
        payload = await self._async_request({"function": "REALTIME_OPTIONS", "symbol": symbol})
        return [self._model(row) for row in payload.get("data", [])]

    async def ahistorical_put_call_ratio(self, symbol: str, date: str | None = None):
        payload = await self._async_request(
            _prune({"function": "HISTORICAL_OPTIONS", "symbol": symbol, "date": date}),
        )
        return [self._model(row) for row in payload.get("data", [])]

    async def arealtime_voi_ratio(self, symbol: str):
        return await self.arealtime_put_call_ratio(symbol)

    async def ahistorical_voi_ratio(self, symbol: str, date: str | None = None):
        return await self.ahistorical_put_call_ratio(symbol, date=date)


class Commodities(BaseEndpoint):
    async def aby_name(self, name: str, **params: Any):
        payload = await self._async_request(_prune({"function": name.upper(), **params}))
        return self._model(payload)


class Economics(BaseEndpoint):
    async def aby_name(self, indicator: str, **params: Any):
        payload = await self._async_request(_prune({"function": indicator.upper(), **params}))
        return self._model(payload)


class Technicals(BaseEndpoint):
    def get(self, indicator: str, symbol: str, **params: Any):
        payload = self._sync_request(_prune({"function": indicator.upper(), "symbol": symbol, **params}))
        return self._model(payload)

    async def aget(self, indicator: str, symbol: str, **params: Any):
        payload = await self._async_request(_prune({"function": indicator.upper(), "symbol": symbol, **params}))
        return self._model(payload)


class Indices(BaseEndpoint):
    async def aget(self, key: str, **params: Any):
        payload = await self._async_request(_prune({"function": key.upper(), **params}))
        return self._model(payload)

    async def acatalog(self) -> list[AVModel]:
        return [AVModel.model_validate({"key": key, "name": label}) for key, label in _INDEX_CATALOG.items()]


_INDEX_CATALOG = {
    "REALTIME_BULK_QUOTES": "Realtime bulk index quotes",
    "TIME_SERIES_DAILY": "Daily index series",
    "MARKET_STATUS": "Market status",
}


__all__ = [
    "Commodities",
    "Crypto",
    "Economics",
    "Forex",
    "Fundamentals",
    "Indices",
    "Intelligence",
    "Options",
    "Technicals",
    "TimeSeries",
]
