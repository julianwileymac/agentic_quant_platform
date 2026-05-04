"""Data ingestion — downloads OHLCV bars and writes tidy Parquet files.

Primary source is ``yfinance`` (the default free adapter). The interface
mirrors FinRL's ``DataProcessor`` so additional sources (Alpaca, CCXT,
Binance, WRDS, Tushare, ...) can be plugged in by subclassing
:class:`BaseDataSource`.

Beyond vendor APIs, :class:`LocalCSVSource` and :class:`LocalParquetSource`
read user-owned files from a mounted drive and normalise them into AQP's
Parquet lake so the rest of the pipeline (DuckDB view, Chroma indexing,
backtest, paper trading) works unchanged.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from aqp.config import settings
from aqp.core.types import Exchange, Symbol

logger = logging.getLogger(__name__)
_ALPHA_VANTAGE_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")


def _is_alpha_vantage_requestable_ticker(ticker: str) -> bool:
    raw = str(ticker or "").strip().upper()
    if not raw or raw in {"N/A", "NULL", "NONE"}:
        return False
    return bool(_ALPHA_VANTAGE_TICKER_RE.fullmatch(raw))


# --------------------------------------------------------------------------
# Small coercion helpers shared by the rich per-security fetchers below.
# Kept top-level so the API layer (and tests) can reuse them.
# --------------------------------------------------------------------------


def _coerce_scalar(value: Any) -> Any:
    """Return a JSON-serialisable primitive or ``None``."""
    if value is None:
        return None
    if isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
            return None
        return float(value)
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return _coerce_scalar(value.item())
    except Exception:  # pragma: no cover - numpy always available here
        pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover
            return str(value)
    try:
        return str(value)
    except Exception:  # pragma: no cover
        return None


def _coerce_timestamp(value: Any) -> str | None:
    """Coerce a heterogeneous timestamp-ish value into an ISO-8601 string."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and value != value:  # NaN
            return None
        ts = pd.Timestamp(value)
        ts = ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
        return ts.isoformat()
    except Exception:
        try:
            return str(value)
        except Exception:  # pragma: no cover
            return None


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


class BaseDataSource(ABC):
    """Uniform adapter contract for any market-data vendor (FinRL pattern)."""

    name: str

    @abstractmethod
    def fetch(
        self,
        symbols: Iterable[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame: ...


class YahooFinanceSource(BaseDataSource):
    """Thin wrapper around ``yfinance`` that returns a tidy long-format frame."""

    name = "yahoo"

    @staticmethod
    def _ticker_vt_pairs(symbols: Iterable[str]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for raw in symbols:
            text = str(raw).strip().upper()
            if not text:
                continue
            symbol = Symbol.parse(text)
            pairs.append((symbol.ticker, symbol.vt_symbol))
        return pairs

    def fetch(
        self,
        symbols: Iterable[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        import yfinance as yf

        pairs = self._ticker_vt_pairs(symbols)
        tickers = [ticker for ticker, _ in pairs]
        vt_by_ticker = {ticker: vt_symbol for ticker, vt_symbol in pairs}
        logger.info("yfinance: downloading %d tickers %s..%s (%s)", len(tickers), start, end, interval)

        raw = yf.download(
            tickers=tickers,
            start=str(start),
            end=str(end),
            interval=interval,
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        if raw.empty:
            return pd.DataFrame()

        rows: list[pd.DataFrame] = []
        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in tickers:
                try:
                    sub = raw[ticker].copy()
                except KeyError:
                    continue
                sub = sub.dropna(how="all").reset_index().rename(
                    columns={"Date": "timestamp", "Datetime": "timestamp"}
                )
                sub["vt_symbol"] = vt_by_ticker.get(ticker, Symbol.parse(ticker).vt_symbol)
                rows.append(sub)
        else:
            sub = raw.dropna(how="all").reset_index().rename(
                columns={"Date": "timestamp", "Datetime": "timestamp"}
            )
            sub["vt_symbol"] = vt_by_ticker.get(tickers[0], Symbol.parse(tickers[0]).vt_symbol)
            rows.append(sub)

        if not rows:
            return pd.DataFrame()

        df = pd.concat(rows, ignore_index=True)
        df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
        df = df[["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.dropna().reset_index(drop=True)
        return df

    def fetch_fundamentals(self, symbols: Iterable[str]) -> pd.DataFrame:
        """Best-effort fundamentals via ``yfinance.Ticker(...).info``.

        Returns a tall frame ``ticker, market_cap, trailing_pe, forward_pe,
        price_to_book, sector, industry, dividend_yield``. Missing keys
        default to ``NaN``. Robust to yfinance rate-limits — errors log
        and skip the affected ticker rather than raising.
        """
        import yfinance as yf

        rows: list[dict[str, Any]] = []
        for ticker in symbols:
            try:
                info = yf.Ticker(ticker).info or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("fundamentals failed for %s: %s", ticker, exc)
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "market_cap": info.get("marketCap"),
                    "trailing_pe": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "price_to_book": info.get("priceToBook"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "dividend_yield": info.get("dividendYield"),
                    "beta": info.get("beta"),
                    "shares_outstanding": info.get("sharesOutstanding"),
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Rich per-security endpoints used by the Live Market security view.
    # Each returns a plain ``dict`` so the FastAPI layer can re-emit as
    # JSON without additional marshalling.  Missing data is represented
    # as ``None`` / empty list to keep the contract stable.
    # ------------------------------------------------------------------

    def fetch_fundamentals_one(self, ticker: str) -> dict[str, Any]:
        """Fundamentals dict for a single ticker. Raises on empty payload."""
        import yfinance as yf

        raw = yf.Ticker(ticker)
        info: dict[str, Any] = {}
        try:
            info = raw.info or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("fundamentals: info() failed for %s: %s", ticker, exc)
            info = {}
        fast_info: dict[str, Any] = {}
        try:
            fi = raw.fast_info
            fast_info = {
                "last_price": getattr(fi, "last_price", None),
                "previous_close": getattr(fi, "previous_close", None),
                "open": getattr(fi, "open", None),
                "day_high": getattr(fi, "day_high", None),
                "day_low": getattr(fi, "day_low", None),
                "fifty_day_average": getattr(fi, "fifty_day_average", None),
                "two_hundred_day_average": getattr(fi, "two_hundred_day_average", None),
                "year_high": getattr(fi, "year_high", None),
                "year_low": getattr(fi, "year_low", None),
                "year_change": getattr(fi, "year_change", None),
                "currency": getattr(fi, "currency", None),
                "exchange": getattr(fi, "exchange", None),
            }
        except Exception:  # noqa: BLE001
            fast_info = {}

        if not info and not any(fast_info.values()):
            raise ValueError(f"no fundamentals payload for {ticker!r}")

        def _pick(*keys: str) -> Any:
            for key in keys:
                if info.get(key) is not None:
                    return info[key]
            return None

        return {
            "ticker": ticker,
            "name": _pick("longName", "shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "currency": info.get("currency") or fast_info.get("currency"),
            "exchange": info.get("exchange") or fast_info.get("exchange"),
            "website": info.get("website"),
            "summary": info.get("longBusinessSummary"),
            # Valuation
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "peg_ratio": info.get("pegRatio"),
            # Dividends / shares
            "dividend_yield": info.get("dividendYield"),
            "dividend_rate": info.get("dividendRate"),
            "payout_ratio": info.get("payoutRatio"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            # Risk
            "beta": info.get("beta"),
            # Margins / growth
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "gross_margin": info.get("grossMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "return_on_equity": info.get("returnOnEquity"),
            "return_on_assets": info.get("returnOnAssets"),
            # 52w
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh") or fast_info.get("year_high"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow") or fast_info.get("year_low"),
            "fifty_day_average": info.get("fiftyDayAverage") or fast_info.get("fifty_day_average"),
            "two_hundred_day_average": (
                info.get("twoHundredDayAverage") or fast_info.get("two_hundred_day_average")
            ),
            # Snapshot
            "last_price": fast_info.get("last_price") or info.get("currentPrice"),
            "previous_close": fast_info.get("previous_close") or info.get("previousClose"),
            "day_high": fast_info.get("day_high"),
            "day_low": fast_info.get("day_low"),
        }

    def fetch_news(self, ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        """Recent headlines via yfinance ``.news``.

        Normalises the two schema variants that yfinance has shipped over
        time (``{title, publisher, link, ...}`` vs the 2024 nested
        ``{content: {...}}`` structure) into a flat dict the UI can
        consume directly.
        """
        import yfinance as yf

        try:
            items = yf.Ticker(ticker).news or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("news: yfinance failed for %s: %s", ticker, exc)
            return []

        out: list[dict[str, Any]] = []
        for item in items[: max(1, int(limit))]:
            if not isinstance(item, dict):
                continue
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            title = (
                item.get("title")
                or content.get("title")
                or item.get("headline")
                or ""
            )
            if not title:
                continue
            publisher = (
                item.get("publisher")
                or (content.get("provider") or {}).get("displayName")
                or content.get("publisher")
                or ""
            )
            link = (
                item.get("link")
                or ((content.get("canonicalUrl") or {}).get("url"))
                or ((content.get("clickThroughUrl") or {}).get("url"))
                or ""
            )
            published = (
                item.get("providerPublishTime")
                or content.get("pubDate")
                or content.get("displayTime")
            )
            summary = item.get("summary") or content.get("summary") or ""
            thumbnail = None
            thumb = item.get("thumbnail") or content.get("thumbnail") or {}
            if isinstance(thumb, dict):
                resolutions = thumb.get("resolutions") or []
                if resolutions:
                    thumbnail = resolutions[0].get("url")
            out.append(
                {
                    "title": str(title),
                    "publisher": str(publisher) if publisher else None,
                    "link": str(link) if link else None,
                    "published": _coerce_timestamp(published),
                    "summary": str(summary) if summary else None,
                    "thumbnail": thumbnail,
                    "related": item.get("relatedTickers") or [],
                }
            )
        return out

    def fetch_calendar(self, ticker: str) -> dict[str, Any]:
        """Next earnings + ex-div / payout events, defensively parsed."""
        import yfinance as yf

        tk = yf.Ticker(ticker)
        try:
            cal = tk.calendar
        except Exception as exc:  # noqa: BLE001
            logger.warning("calendar: yfinance failed for %s: %s", ticker, exc)
            cal = None

        payload: dict[str, Any] = {"ticker": ticker}
        if isinstance(cal, dict):
            for key, value in cal.items():
                snake = _camel_to_snake(key)
                payload[snake] = _coerce_scalar(value)
        elif hasattr(cal, "empty") and not cal.empty:  # pragma: no cover - old pandas shape
            record = cal.to_dict()
            for key, inner in record.items():
                snake = _camel_to_snake(str(key))
                if isinstance(inner, dict) and inner:
                    payload[snake] = _coerce_scalar(next(iter(inner.values())))

        try:
            ed = tk.earnings_dates
            if ed is not None and not ed.empty:
                payload["earnings_history"] = [
                    {
                        "date": _coerce_timestamp(idx),
                        "eps_estimate": _coerce_scalar(row.get("EPS Estimate")),
                        "eps_actual": _coerce_scalar(row.get("Reported EPS")),
                        "surprise_pct": _coerce_scalar(row.get("Surprise(%)")),
                    }
                    for idx, row in ed.head(8).iterrows()
                ]
        except Exception:  # noqa: BLE001
            pass

        return payload

    def fetch_corporate_actions(self, ticker: str) -> dict[str, Any]:
        """Dividends, splits and (when available) top institutional holders."""
        import yfinance as yf

        tk = yf.Ticker(ticker)

        def _series_to_list(series) -> list[dict[str, Any]]:
            if series is None:
                return []
            try:
                if series.empty:  # type: ignore[union-attr]
                    return []
            except Exception:
                return []
            return [
                {"date": _coerce_timestamp(idx), "value": _coerce_scalar(val)}
                for idx, val in series.items()
            ]

        try:
            dividends = _series_to_list(tk.dividends)
        except Exception:  # noqa: BLE001
            dividends = []
        try:
            splits = _series_to_list(tk.splits)
        except Exception:  # noqa: BLE001
            splits = []

        holders: list[dict[str, Any]] = []
        try:
            hdf = tk.institutional_holders
            if hdf is not None and not hdf.empty:
                for _, row in hdf.head(15).iterrows():
                    holders.append(
                        {
                            "holder": _coerce_scalar(row.get("Holder")),
                            "shares": _coerce_scalar(row.get("Shares")),
                            "date_reported": _coerce_timestamp(row.get("Date Reported")),
                            "percent_out": _coerce_scalar(row.get("% Out") or row.get("pctHeld")),
                            "value": _coerce_scalar(row.get("Value")),
                        }
                    )
        except Exception:  # noqa: BLE001
            holders = []

        return {
            "ticker": ticker,
            "dividends": dividends,
            "splits": splits,
            "institutional_holders": holders,
        }

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Snapshot quote from yfinance ``fast_info``. Zero-network fallback to info."""
        import yfinance as yf

        tk = yf.Ticker(ticker)
        last = prev = currency = None
        try:
            fi = tk.fast_info
            last = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            currency = getattr(fi, "currency", None)
            open_ = getattr(fi, "open", None)
            day_high = getattr(fi, "day_high", None)
            day_low = getattr(fi, "day_low", None)
            volume = getattr(fi, "last_volume", None) or getattr(fi, "ten_day_average_volume", None)
        except Exception:  # noqa: BLE001
            open_ = day_high = day_low = volume = None

        if last is None or prev is None:
            try:
                info = tk.info or {}
            except Exception:  # noqa: BLE001
                info = {}
            last = last or info.get("currentPrice") or info.get("regularMarketPrice")
            prev = prev or info.get("previousClose") or info.get("regularMarketPreviousClose")
            currency = currency or info.get("currency")
            open_ = open_ or info.get("open") or info.get("regularMarketOpen")
            day_high = day_high or info.get("dayHigh") or info.get("regularMarketDayHigh")
            day_low = day_low or info.get("dayLow") or info.get("regularMarketDayLow")
            volume = volume or info.get("regularMarketVolume") or info.get("volume")

        change: float | None = None
        change_pct: float | None = None
        if last is not None and prev not in (None, 0):
            try:
                change = float(last) - float(prev)
                change_pct = (change / float(prev)) * 100.0
            except (TypeError, ValueError):
                change = change_pct = None

        if last is None:
            raise ValueError(f"no quote snapshot for {ticker!r}")

        return {
            "ticker": ticker,
            "last": _coerce_scalar(last),
            "previous_close": _coerce_scalar(prev),
            "change": _coerce_scalar(change),
            "change_pct": _coerce_scalar(change_pct),
            "open": _coerce_scalar(open_),
            "day_high": _coerce_scalar(day_high),
            "day_low": _coerce_scalar(day_low),
            "volume": _coerce_scalar(volume),
            "currency": currency,
            "timestamp": _coerce_timestamp(pd.Timestamp.utcnow()),
        }


class AlpacaSource(BaseDataSource):
    name = "alpaca"

    def fetch(self, *args, **kwargs):  # pragma: no cover — extension hook
        raise NotImplementedError(
            "Plug in alpaca-trade-api here. See FinRL's AlpacaDownloader."
        )


class CCXTSource(BaseDataSource):
    name = "ccxt"

    def fetch(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError(
            "Plug in ccxt for crypto venues (Binance/Coinbase/...)."
        )


class PolygonSource(BaseDataSource):
    """Polygon.io REST template.

    Hits ``/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}`` and
    normalises to the canonical tidy schema. Requires
    ``AQP_POLYGON_API_KEY`` in the environment (added as a soft setting
    so the base install doesn't need a real key).
    """

    name = "polygon"

    def __init__(self, api_key: str | None = None) -> None:
        import os

        self.api_key = api_key or os.environ.get("AQP_POLYGON_API_KEY", "")

    def fetch(
        self,
        symbols: Iterable[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError("PolygonSource requires AQP_POLYGON_API_KEY")
        import httpx

        rows: list[pd.DataFrame] = []
        multiplier, timespan = _polygon_interval(interval)
        start_str = pd.Timestamp(start).strftime("%Y-%m-%d")
        end_str = pd.Timestamp(end).strftime("%Y-%m-%d")
        with httpx.Client(timeout=30.0) as client:
            for ticker in symbols:
                url = (
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
                    f"{multiplier}/{timespan}/{start_str}/{end_str}"
                )
                resp = client.get(url, params={"apiKey": self.api_key, "limit": 50000})
                resp.raise_for_status()
                results = resp.json().get("results") or []
                if not results:
                    continue
                df = pd.DataFrame(results).rename(
                    columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df["vt_symbol"] = f"{ticker}.{Exchange.NASDAQ.value}"
                rows.append(df[["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]])
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _polygon_interval(interval: str) -> tuple[int, str]:
    mapping = {"1m": (1, "minute"), "5m": (5, "minute"), "1h": (1, "hour"), "1d": (1, "day"), "1w": (1, "week")}
    return mapping.get(interval, (1, "day"))


class AlphaVantageSource(BaseDataSource):
    """Alpha Vantage historical bars source backed by the rich AQP client."""

    name = "alpha_vantage"

    def __init__(
        self,
        api_key: str | None = None,
        client: Any | None = None,
        *,
        close_after_fetch: bool = True,
    ) -> None:
        self.api_key = api_key or settings.alpha_vantage_api_key
        self.client = client
        self._owns_client = client is None
        self.close_after_fetch = bool(close_after_fetch)

    def close(self) -> None:
        if self._owns_client and self.client is not None:
            self.client.close()

    @staticmethod
    def _ticker_vt_pairs(symbols: Iterable[str]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for raw in symbols:
            text = str(raw).strip().upper()
            if not text:
                continue
            symbol = Symbol.parse(text)
            pairs.append((symbol.ticker, symbol.vt_symbol))
        return pairs

    def fetch(
        self,
        symbols: Iterable[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        from aqp.data.sources.alpha_vantage import AlphaVantageClient
        from aqp.data.sources.alpha_vantage._errors import AlphaVantagePayloadError

        rows: list[pd.DataFrame] = []
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        client = self.client or AlphaVantageClient(api_key=self.api_key)
        self.client = client
        try:
            for ticker, vt_symbol in self._ticker_vt_pairs(symbols):
                if not _is_alpha_vantage_requestable_ticker(ticker):
                    logger.info("alpha_vantage: skipping unsupported ticker %s (%s)", ticker, vt_symbol)
                    continue
                try:
                    if str(interval).endswith("m") or str(interval).endswith("min"):
                        payload = client.timeseries.intraday(
                            ticker,
                            interval=str(interval).replace("m", "min"),
                            outputsize="full",
                        )
                    else:
                        payload = client.timeseries.daily_adjusted(ticker, outputsize="full")
                except AlphaVantagePayloadError as exc:
                    logger.info("alpha_vantage: skipping %s (%s): %s", ticker, vt_symbol, exc)
                    continue
                if not payload.bars:
                    continue
                df = pd.DataFrame(payload.bars)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.rename(
                    columns={
                        "adjusted_close": "adj_close",
                    }
                )
                for col in ("open", "high", "low", "close", "volume"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].sort_values("timestamp")
                df["vt_symbol"] = vt_symbol
                rows.append(df[["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]])
        finally:
            if self._owns_client and self.close_after_fetch:
                client.close()
                self.client = None
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


class IBKRHistoricalSource(BaseDataSource):
    """IBKR historical bars adapter backed by :mod:`aqp.data.ibkr_historical`."""

    name = "ibkr-historical"

    def __init__(
        self,
        *,
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> None:
        self.bar_size = bar_size
        self.what_to_show = what_to_show
        self.use_rth = bool(use_rth)
        self.exchange = exchange
        self.currency = currency

    def fetch(
        self,
        symbols: Iterable[str],
        start: datetime | str,
        end: datetime | str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        from aqp.data.ibkr_historical import IBKRHistoricalService

        bar_size = self.bar_size or _interval_to_ib_bar_size(interval)
        service = IBKRHistoricalService(exchange=self.exchange, currency=self.currency)
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            coro = service.fetch_bars(
                vt_symbol=symbol,
                start=start,
                end=end,
                bar_size=bar_size,
                what_to_show=self.what_to_show,
                use_rth=self.use_rth,
                exchange=self.exchange,
                currency=self.currency,
            )
            try:
                frame = asyncio.run(coro)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    frame = loop.run_until_complete(coro)
                finally:
                    loop.close()
            if not frame.empty:
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _interval_to_ib_bar_size(interval: str) -> str:
    mapping = {
        "1s": "1 secs",
        "5s": "5 secs",
        "10s": "10 secs",
        "15s": "15 secs",
        "30s": "30 secs",
        "1m": "1 min",
        "2m": "2 mins",
        "3m": "3 mins",
        "5m": "5 mins",
        "10m": "10 mins",
        "15m": "15 mins",
        "20m": "20 mins",
        "30m": "30 mins",
        "1h": "1 hour",
        "2h": "2 hours",
        "3h": "3 hours",
        "4h": "4 hours",
        "8h": "8 hours",
        "1d": "1 day",
    }
    return mapping.get(interval, "1 day")


# -------------------------------------------------------------------------
# Local-drive sources — read user-owned files from a mounted filesystem.
# -------------------------------------------------------------------------


_CANONICAL_COLUMNS = ["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]
_DEFAULT_COLUMN_MAP: dict[str, str] = {
    "timestamp": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "time": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj close": "close",
    "adj_close": "close",
    "adjusted close": "close",
    "volume": "volume",
    "vol": "volume",
    "symbol": "vt_symbol",
    "ticker": "vt_symbol",
    "vt_symbol": "vt_symbol",
}


def _normalise_frame(
    df: pd.DataFrame,
    *,
    default_vt_symbol: str | None = None,
    column_map: dict[str, str] | None = None,
    tz: str | None = None,
) -> pd.DataFrame:
    """Coerce a user DataFrame into the canonical tidy bars schema."""
    if df.empty:
        return df
    mapping = {str(k).strip().lower(): v for k, v in (column_map or _DEFAULT_COLUMN_MAP).items()}
    renamed: dict[str, str] = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in mapping:
            renamed[col] = mapping[key]
    df = df.rename(columns=renamed)

    if "vt_symbol" not in df.columns and default_vt_symbol:
        df["vt_symbol"] = default_vt_symbol
    missing = set(_CANONICAL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"Local data is missing required columns {sorted(missing)}; "
            "either rename columns, pass column_map=, or set symbol via filename."
        )
    df = df[_CANONICAL_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    if tz:
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(tz)
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert(tz)
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "vt_symbol", "open", "high", "low", "close"])
    return df.reset_index(drop=True)


def _vt_from_filename(path: Path, default_exchange: Exchange = Exchange.LOCAL) -> str:
    stem = path.stem.upper()
    stem = re.sub(r"[^A-Z0-9_.-]", "", stem)
    if "." in stem:
        return stem
    if "_" in stem:
        ticker, _, exch = stem.rpartition("_")
        try:
            Exchange(exch)
            return f"{ticker}.{exch}"
        except ValueError:
            pass
    return f"{stem}.{default_exchange.value}"


def _iter_files(path: Path, glob: str) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    yield from sorted(path.rglob(glob))


class LocalCSVSource(BaseDataSource):
    """Read CSV files from a directory (or a single file) into tidy bars."""

    name = "local-csv"

    def __init__(
        self,
        root: Path | str,
        glob: str = "*.csv",
        column_map: dict[str, str] | None = None,
        tz: str | None = None,
        default_exchange: Exchange = Exchange.LOCAL,
        map_file_dir: Path | str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.glob = glob
        self.column_map = column_map
        self.tz = tz
        self.default_exchange = default_exchange
        self.map_file_dir = Path(map_file_dir).expanduser().resolve() if map_file_dir else None

    def fetch(
        self,
        symbols: Iterable[str] | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        del interval  # unused — local bars are whatever cadence the files are at
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        wanted = {s for s in (symbols or ())}
        frames: list[pd.DataFrame] = []
        for path in _iter_files(self.root, self.glob):
            try:
                raw = pd.read_csv(path)
            except Exception:
                logger.exception("could not parse CSV %s — skipping", path)
                continue
            df = _normalise_frame(
                raw,
                default_vt_symbol=_vt_from_filename(path, self.default_exchange),
                column_map=self.column_map,
                tz=self.tz,
            )
            if not df.empty and self.map_file_dir:
                df = self._apply_asof_mapping(df, path)
            if not df.empty:
                frames.append(df)
        return _filter(frames, wanted, start, end)

    def _apply_asof_mapping(self, df: pd.DataFrame, file_path: Path) -> pd.DataFrame:
        """Apply per-symbol ``MapFile`` rewrites (ticker renames over time)."""
        try:
            from aqp.core.corporate_actions import MapFile
        except Exception:  # pragma: no cover
            return df
        assert self.map_file_dir is not None
        vt_symbol = df["vt_symbol"].iloc[0]
        safe = vt_symbol.replace(".", "_")
        map_path = self.map_file_dir / f"{safe}.csv"
        if not map_path.exists():
            return df
        try:
            map_file = MapFile.load(map_path)
        except Exception:
            logger.exception("could not load map file %s", map_path)
            return df
        # Rewrite ticker based on timestamp
        exchange = vt_symbol.split(".")[-1]
        df = df.copy()
        df["vt_symbol"] = df["timestamp"].apply(
            lambda ts: f"{map_file.ticker_at(ts)}.{exchange}"
        )
        return df


class LocalParquetSource(BaseDataSource):
    """Read Parquet files from a directory (or a single file) into tidy bars."""

    name = "local-parquet"

    def __init__(
        self,
        root: Path | str,
        glob: str = "*.parquet",
        column_map: dict[str, str] | None = None,
        tz: str | None = None,
        default_exchange: Exchange = Exchange.LOCAL,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.glob = glob
        self.column_map = column_map
        self.tz = tz
        self.default_exchange = default_exchange

    def fetch(
        self,
        symbols: Iterable[str] | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        del interval
        if not self.root.exists():
            raise FileNotFoundError(self.root)
        wanted = {s for s in (symbols or ())}
        frames: list[pd.DataFrame] = []
        for path in _iter_files(self.root, self.glob):
            try:
                raw = pd.read_parquet(path)
            except Exception:
                logger.exception("could not parse Parquet %s — skipping", path)
                continue
            df = _normalise_frame(
                raw,
                default_vt_symbol=_vt_from_filename(path, self.default_exchange),
                column_map=self.column_map,
                tz=self.tz,
            )
            if not df.empty:
                frames.append(df)
        return _filter(frames, wanted, start, end)


def _filter(
    frames: list[pd.DataFrame],
    wanted: set[str],
    start: datetime | str | None,
    end: datetime | str | None,
) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=_CANONICAL_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    if wanted:
        df = df[df["vt_symbol"].isin(wanted)]
    if start is not None:
        df = df[df["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["timestamp"] <= pd.Timestamp(end)]
    df = df.drop_duplicates(subset=["timestamp", "vt_symbol"]).sort_values(
        ["timestamp", "vt_symbol"]
    )
    return df.reset_index(drop=True)


class LocalDirectoryLoader:
    """Top-level helper: read a directory, normalise, and merge into AQP's lake.

    Reads every file under ``source_dir`` matching ``glob``, normalises to
    the canonical tidy bars schema, and writes to the AQP Parquet lake via
    :func:`write_parquet`. Returns the root path written to.
    """

    def __init__(
        self,
        source_dir: Path | str,
        *,
        format: str = "csv",
        glob: str | None = None,
        column_map: dict[str, str] | None = None,
        tz: str | None = None,
        default_exchange: Exchange = Exchange.LOCAL,
    ) -> None:
        self.source_dir = Path(source_dir).expanduser().resolve()
        self.format = format.lower()
        self.glob = glob or ("*.csv" if self.format == "csv" else "*.parquet")
        self.column_map = column_map
        self.tz = tz
        self.default_exchange = default_exchange

    def run(
        self,
        target_dir: Path | str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        source: BaseDataSource
        if self.format == "csv":
            source = LocalCSVSource(
                self.source_dir,
                glob=self.glob,
                column_map=self.column_map,
                tz=self.tz,
                default_exchange=self.default_exchange,
            )
        elif self.format in {"parquet", "pq"}:
            source = LocalParquetSource(
                self.source_dir,
                glob=self.glob,
                column_map=self.column_map,
                tz=self.tz,
                default_exchange=self.default_exchange,
            )
        else:
            raise ValueError(f"unsupported format: {self.format!r}")
        df = source.fetch()
        if df.empty:
            logger.warning("LocalDirectoryLoader: no rows parsed from %s", self.source_dir)
            return {
                "source_dir": str(self.source_dir),
                "rows": 0,
                "symbols": [],
                "target": None,
            }
        target = write_parquet(df, parquet_dir=target_dir, overwrite=overwrite)
        lineage: dict[str, Any] = {}
        try:
            from aqp.data.catalog import register_dataset_version

            lineage = register_dataset_version(
                name="bars.local",
                provider=f"local-{self.format}",
                domain="market.bars",
                df=df,
                storage_uri=str(target),
                frequency=None,
                meta={
                    "source_dir": str(self.source_dir),
                    "glob": self.glob,
                    "overwrite": bool(overwrite),
                },
                file_count=len(list(_iter_files(self.source_dir, self.glob))),
            )
        except Exception:
            logger.debug("LocalDirectoryLoader lineage registration failed", exc_info=True)
        return {
            "source_dir": str(self.source_dir),
            "target": str(target),
            "rows": int(len(df)),
            "symbols": sorted(df["vt_symbol"].unique().tolist()),
            **lineage,
        }


# -------------------------------------------------------------------------


def write_parquet(df: pd.DataFrame, parquet_dir: Path | str | None = None, overwrite: bool = False) -> Path:
    """Write a tidy bars frame as one Parquet file per ``vt_symbol``."""
    root = Path(parquet_dir or settings.parquet_dir) / "bars"
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for vt_symbol, sub in df.groupby("vt_symbol", sort=False):
        safe_name = vt_symbol.replace(".", "_")
        out = root / f"{safe_name}.parquet"
        if out.exists() and not overwrite:
            existing = pd.read_parquet(out)
            combined = (
                pd.concat([existing, sub], ignore_index=True)
                .drop_duplicates(subset=["timestamp", "vt_symbol"])
                .sort_values("timestamp")
            )
            pq.write_table(pa.Table.from_pandas(combined), out)
        else:
            pq.write_table(pa.Table.from_pandas(sub.sort_values("timestamp")), out)
        written.append(out)
        logger.info("wrote %s rows → %s", len(sub), out)
    return root


def dataset_hash(df: pd.DataFrame) -> str:
    """Stable SHA256 of a bars frame — used for MLflow lineage."""
    buf = pd.util.hash_pandas_object(df, index=False).values.tobytes()
    return hashlib.sha256(buf).hexdigest()


def _alpha_vantage_configured() -> bool:
    return bool(str(settings.alpha_vantage_api_key or "").strip())


def _source_name(source: BaseDataSource) -> str:
    return str(getattr(source, "name", source.__class__.__name__)).strip().lower()


def _source_from_name(name: str) -> BaseDataSource:
    raw = str(name or "").strip().lower()
    mapping: dict[str, type[BaseDataSource]] = {
        "yahoo": YahooFinanceSource,
        "yfinance": YahooFinanceSource,
        "alpha_vantage": AlphaVantageSource,
        "alphavantage": AlphaVantageSource,
        "polygon": PolygonSource,
        "ibkr": IBKRHistoricalSource,
        "ibkr-historical": IBKRHistoricalSource,
        "ccxt": CCXTSource,
    }
    cls = mapping.get(raw)
    if cls is None:
        raise ValueError(f"unknown market-bars source {name!r}")
    return cls()


def _resolve_market_bars_source(source: BaseDataSource | str | None = None) -> BaseDataSource:
    if isinstance(source, BaseDataSource):
        return source
    if isinstance(source, str) and source.strip():
        raw = source.strip().lower()
        if raw == "auto":
            return _resolve_market_bars_source(None)
        return _source_from_name(raw)

    policy = str(settings.market_bars_provider or "auto").strip().lower()
    if policy == "yfinance":
        return YahooFinanceSource()
    if policy == "alpha_vantage":
        if _alpha_vantage_configured():
            return AlphaVantageSource()
        logger.warning("market_bars_provider=alpha_vantage but no API key configured; falling back to yfinance")
        return YahooFinanceSource()

    # auto
    if _alpha_vantage_configured():
        return AlphaVantageSource()
    return YahooFinanceSource()


def _fetch_with_fallback(
    source: BaseDataSource,
    *,
    symbols: list[str],
    start: datetime | str,
    end: datetime | str,
    interval: str,
    allow_fallback: bool = True,
) -> tuple[pd.DataFrame, BaseDataSource]:
    try:
        df = source.fetch(symbols, start, end, interval)
    except Exception as exc:
        if _source_name(source) == "yahoo" or not allow_fallback:
            raise
        logger.warning("primary source %s failed (%s); falling back to yfinance", _source_name(source), exc)
        fallback = YahooFinanceSource()
        return fallback.fetch(symbols, start, end, interval), fallback

    if not df.empty or _source_name(source) == "yahoo" or not allow_fallback:
        return df, source

    logger.warning("primary source %s returned no rows; falling back to yfinance", _source_name(source))
    fallback = YahooFinanceSource()
    return fallback.fetch(symbols, start, end, interval), fallback


def _resolve_ingest_symbols(symbols: Iterable[str] | None) -> list[str]:
    if symbols:
        return [str(s).strip().upper() for s in symbols if str(s).strip()]

    policy = str(settings.universe_provider or "managed_snapshot").strip().lower()
    if policy == "managed_snapshot":
        try:
            from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

            snapshot_symbols = AlphaVantageUniverseService().default_symbols()
            if snapshot_symbols:
                return snapshot_symbols
        except Exception as exc:
            logger.info("managed snapshot universe unavailable: %s", exc)

    return [str(s).strip().upper() for s in settings.universe_list if str(s).strip()]


def ingest(
    symbols: Iterable[str] | None = None,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    interval: str = "1d",
    source: BaseDataSource | str | None = None,
    *,
    register_catalog_version: bool = True,
) -> pd.DataFrame:
    """High-level one-shot: fetch + write + return the frame."""
    symbols = _resolve_ingest_symbols(symbols)
    start = start or settings.default_start
    end = end or settings.default_end

    resolved_source = _resolve_market_bars_source(source)
    allow_fallback = source is None or (isinstance(source, str) and source.strip().lower() == "auto")
    logger.info(
        "ingest provider=%s symbols=%d start=%s end=%s interval=%s",
        _source_name(resolved_source),
        len(symbols),
        start,
        end,
        interval,
    )

    df, resolved_source = _fetch_with_fallback(
        resolved_source,
        symbols=symbols,
        start=start,
        end=end,
        interval=interval,
        allow_fallback=allow_fallback,
    )
    if df.empty:
        logger.warning("No data fetched; aborting write.")
        return df

    path = write_parquet(df)
    lineage: dict[str, Any] = {}
    if register_catalog_version:
        try:
            from aqp.data.catalog import register_dataset_version

            lineage = register_dataset_version(
                name="bars.default",
                provider=getattr(resolved_source, "name", "unknown"),
                domain="market.bars",
                df=df,
                storage_uri=str(path),
                frequency=interval,
                meta={
                    "symbols": symbols,
                    "start": str(start),
                    "end": str(end),
                    "interval": interval,
                },
                file_count=int(df["vt_symbol"].nunique()),
            )
            if lineage:
                df.attrs["lineage"] = lineage
        except Exception:
            logger.debug("ingest lineage registration failed", exc_info=True)
    logger.info("Ingestion complete: %d rows across %d symbols → %s", len(df), df["vt_symbol"].nunique(), path)
    return df


def iter_symbols(df: pd.DataFrame) -> list[Symbol]:
    return [Symbol.parse(vt) for vt in df["vt_symbol"].unique()]
