"""Individual stream coroutines.

Each stream is a ``async def run(app, cfg)`` coroutine that loops until the app
shuts down, spacing its polls by ``cfg.interval_seconds``. Streams share the
app's rate limiter so aggregate API pressure never exceeds ``AV_PRODUCER_RPM_LIMIT``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List

from alphavantage_client._parsers import to_epoch_ns

from .app import API_REQUESTS, classify_av_error
from .config import StreamConfig

if TYPE_CHECKING:
    from .app import AlphaVantageProducerApp

logger = logging.getLogger(__name__)


StreamRunner = Callable[["AlphaVantageProducerApp", StreamConfig], Awaitable[None]]


async def _safe_call(
    app: "AlphaVantageProducerApp",
    *,
    stream: str,
    target_topic: str,
    function: str,
    params: Dict[str, Any],
    coroutine: Awaitable[Any],
) -> Any:
    """Invoke ``coroutine`` with metrics + deadletter routing."""

    started = time.perf_counter()
    try:
        result = await coroutine
    except Exception as exc:  # noqa: BLE001
        API_REQUESTS.labels(stream=stream, function=function).observe(
            time.perf_counter() - started,
        )
        kind = classify_av_error(exc)
        retry_after = getattr(exc, "retry_after_seconds", None)
        app.send_deadletter(
            stream=stream,
            target_topic=target_topic,
            av_function=function,
            error_kind=kind,
            error_message=str(exc),
            request_params=params,
            retry_after_seconds=retry_after,
        )
        return None
    API_REQUESTS.labels(stream=stream, function=function).observe(
        time.perf_counter() - started,
    )
    return result


def _now_ns() -> int:
    return time.time_ns()


# ---------------------------------------------------------------------------
# Quote stream (GLOBAL_QUOTE per symbol)
# ---------------------------------------------------------------------------


async def quote_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_quote
    symbols = list(app.runtime.universe.equities)
    if not symbols:
        logger.info("quote stream has no symbols configured; exiting")
        return
    interval = cfg.interval_seconds
    while True:
        for symbol in symbols:
            quote = await _safe_call(
                app,
                stream="quote",
                target_topic=topic,
                function="GLOBAL_QUOTE",
                params={"symbol": symbol},
                coroutine=app.client.timeseries.aglobal_quote(symbol),
            )
            if quote is None:
                continue
            latest_day = quote.latest_trading_day
            record = {
                "ts_ns": to_epoch_ns(latest_day) or _now_ns(),
                "symbol": symbol,
                "open": quote.open,
                "high": quote.high,
                "low": quote.low,
                "price": quote.price,
                "volume": int(quote.volume) if quote.volume is not None else None,
                "latest_trading_day": latest_day,
                "previous_close": quote.previous_close,
                "change": quote.change,
                "change_percent": quote.change_percent,
                "entitlement": None,
                "av_function": "GLOBAL_QUOTE",
                "ingest_ts_ns": _now_ns(),
            }
            app.publish(stream="quote", topic=topic, schema="alphavantage_quote_v1", record=record, key=symbol)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Bar stream (TIME_SERIES_INTRADAY tail)
# ---------------------------------------------------------------------------


async def bar_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_bar
    interval = cfg.interval_seconds
    bar_interval = str(cfg.extras.get("interval", "5min"))
    outputsize = str(cfg.extras.get("outputsize", "compact"))
    seen: Dict[str, str] = {}
    symbols = list(app.runtime.universe.equities)
    while True:
        for symbol in symbols:
            params = {"interval": bar_interval, "outputsize": outputsize, "symbol": symbol}
            payload = await _safe_call(
                app,
                stream="bar",
                target_topic=topic,
                function="TIME_SERIES_INTRADAY",
                params=params,
                coroutine=app.client.timeseries.aintraday(
                    symbol,
                    interval=bar_interval,
                    outputsize=outputsize,
                ),
            )
            if payload is None or not payload.bars:
                continue
            new_bars = []
            last_ts = seen.get(symbol)
            for bar in payload.bars:
                if last_ts and bar.timestamp <= last_ts:
                    continue
                new_bars.append(bar)
            if not new_bars:
                continue
            for bar in new_bars:
                record = {
                    "ts_ns": to_epoch_ns(bar.timestamp) or _now_ns(),
                    "symbol": symbol,
                    "interval": bar_interval,
                    "open": bar.open or 0.0,
                    "high": bar.high or 0.0,
                    "low": bar.low or 0.0,
                    "close": bar.close or 0.0,
                    "adjusted_close": bar.adjusted_close,
                    "volume": bar.volume or 0.0,
                    "dividend_amount": bar.dividend_amount,
                    "split_coefficient": bar.split_coefficient,
                    "entitlement": None,
                    "av_function": "TIME_SERIES_INTRADAY",
                    "ingest_ts_ns": _now_ns(),
                }
                app.publish(
                    stream="bar",
                    topic=topic,
                    schema="alphavantage_bar_v1",
                    record=record,
                    key=symbol,
                )
            seen[symbol] = max(bar.timestamp for bar in new_bars)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# FX stream
# ---------------------------------------------------------------------------


async def fx_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_fx
    pairs = list(app.runtime.universe.fx_pairs)
    interval = cfg.interval_seconds
    if not pairs:
        return
    while True:
        for pair in pairs:
            frm = pair.get("from") or pair.get("from_currency") or ""
            to = pair.get("to") or pair.get("to_currency") or ""
            if not frm or not to:
                continue
            rate = await _safe_call(
                app,
                stream="fx",
                target_topic=topic,
                function="CURRENCY_EXCHANGE_RATE",
                params={"from_currency": frm, "to_currency": to},
                coroutine=app.client.forex.aexchange_rate(frm, to),
            )
            if rate is None:
                continue
            record = {
                "ts_ns": to_epoch_ns(rate.last_refreshed) or _now_ns(),
                "from_currency": frm,
                "to_currency": to,
                "rate_kind": "REALTIME",
                "interval": None,
                "open": None,
                "high": None,
                "low": None,
                "close": None,
                "exchange_rate": rate.exchange_rate,
                "bid_price": rate.bid_price,
                "ask_price": rate.ask_price,
                "av_function": "CURRENCY_EXCHANGE_RATE",
                "ingest_ts_ns": _now_ns(),
            }
            app.publish(
                stream="fx",
                topic=topic,
                schema="alphavantage_fx_v1",
                record=record,
                key=f"{frm}/{to}",
            )
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Crypto stream (CRYPTO_INTRADAY tail)
# ---------------------------------------------------------------------------


async def crypto_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_crypto
    pairs = list(app.runtime.universe.crypto_pairs)
    bar_interval = str(cfg.extras.get("interval", "5min"))
    interval = cfg.interval_seconds
    seen: Dict[str, str] = {}
    if not pairs:
        return
    while True:
        for pair in pairs:
            symbol = pair.get("symbol") or ""
            market = pair.get("market") or "USD"
            if not symbol:
                continue
            payload = await _safe_call(
                app,
                stream="crypto",
                target_topic=topic,
                function="CRYPTO_INTRADAY",
                params={"symbol": symbol, "market": market, "interval": bar_interval},
                coroutine=app.client.crypto.aintraday(symbol, market, interval=bar_interval),
            )
            if payload is None or not payload.bars:
                continue
            key = f"{symbol}:{market}"
            last_ts = seen.get(key)
            new_bars = [b for b in payload.bars if not last_ts or b.timestamp > last_ts]
            if not new_bars:
                continue
            for bar in new_bars:
                record = {
                    "ts_ns": to_epoch_ns(bar.timestamp) or _now_ns(),
                    "symbol": symbol,
                    "market": market,
                    "quote_kind": "INTRADAY",
                    "interval": bar_interval,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "market_cap": bar.market_cap,
                    "exchange_rate": None,
                    "bid_price": None,
                    "ask_price": None,
                    "av_function": "CRYPTO_INTRADAY",
                    "ingest_ts_ns": _now_ns(),
                }
                app.publish(
                    stream="crypto",
                    topic=topic,
                    schema="alphavantage_crypto_v1",
                    record=record,
                    key=key,
                )
            seen[key] = max(bar.timestamp for bar in new_bars)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# News stream (NEWS_SENTIMENT)
# ---------------------------------------------------------------------------


async def news_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_news
    interval = cfg.interval_seconds
    tickers: List[str] = cfg.extras.get("tickers", app.runtime.universe.equities) or []
    topics: List[str] = cfg.extras.get("topics", []) or []
    seen: set[str] = set()
    while True:
        payload = await _safe_call(
            app,
            stream="news",
            target_topic=topic,
            function="NEWS_SENTIMENT",
            params={"tickers": ",".join(tickers), "topics": ",".join(topics)},
            coroutine=app.client.intelligence.anews(tickers=tickers or None, topics=topics or None),
        )
        if payload is not None and payload.feed:
            for article in payload.feed:
                article_url = article.url or ""
                if not article_url:
                    continue
                article_id = hashlib.sha256(article_url.encode("utf-8")).hexdigest()
                if article_id in seen:
                    continue
                seen.add(article_id)
                record = {
                    "ts_ns": to_epoch_ns(article.time_published) or _now_ns(),
                    "article_id": article_id,
                    "url": article_url,
                    "title": article.title,
                    "summary": article.summary,
                    "banner_image": article.banner_image,
                    "source": article.source,
                    "source_domain": article.source_domain,
                    "category_within_source": article.category_within_source,
                    "authors": list(article.authors or []),
                    "topics": [
                        {"topic": t.topic or "", "relevance_score": t.relevance_score}
                        for t in (article.topics or [])
                    ],
                    "ticker_sentiment": [
                        {
                            "ticker": ts.ticker or "",
                            "relevance_score": ts.relevance_score,
                            "ticker_sentiment_score": ts.ticker_sentiment_score,
                            "ticker_sentiment_label": ts.ticker_sentiment_label,
                        }
                        for ts in (article.ticker_sentiment or [])
                    ],
                    "overall_sentiment_score": article.overall_sentiment_score,
                    "overall_sentiment_label": article.overall_sentiment_label,
                    "av_function": "NEWS_SENTIMENT",
                    "ingest_ts_ns": _now_ns(),
                }
                app.publish(
                    stream="news",
                    topic=topic,
                    schema="alphavantage_news_v1",
                    record=record,
                    key=article_id,
                )
            # Keep the seen set bounded.
            if len(seen) > 5000:
                seen = set(list(seen)[-2500:])
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Top-gainers/losers stream
# ---------------------------------------------------------------------------


async def gainers_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_gainers
    interval = cfg.interval_seconds
    while True:
        payload = await _safe_call(
            app,
            stream="gainers",
            target_topic=topic,
            function="TOP_GAINERS_LOSERS",
            params={},
            coroutine=app.client.intelligence.atop_movers(),
        )
        if payload is not None:
            groups = (
                ("TOP_GAINER", payload.top_gainers),
                ("TOP_LOSER", payload.top_losers),
                ("MOST_ACTIVELY_TRADED", payload.most_actively_traded),
            )
            for bucket, items in groups:
                for rank, mover in enumerate(items or [], start=1):
                    record = {
                        "ts_ns": _now_ns(),
                        "bucket": bucket,
                        "rank": rank,
                        "ticker": mover.ticker or "",
                        "price": _maybe_float(mover.price),
                        "change_amount": _maybe_float(mover.change_amount),
                        "change_percentage": _maybe_pct(mover.change_percentage),
                        "volume": int(float(mover.volume)) if mover.volume else None,
                        "last_updated": payload.last_updated,
                        "av_function": "TOP_GAINERS_LOSERS",
                        "ingest_ts_ns": _now_ns(),
                    }
                    app.publish(
                        stream="gainers",
                        topic=topic,
                        schema="alphavantage_gainers_v1",
                        record=record,
                        key=f"{bucket}:{mover.ticker}",
                    )
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Technical indicator stream (driven by runtime.indicators)
# ---------------------------------------------------------------------------


async def indicator_stream(app: "AlphaVantageProducerApp", cfg: StreamConfig) -> None:
    topic = app.settings.topic_indicator
    definitions = list(app.runtime.indicators)
    interval = cfg.interval_seconds
    seen: Dict[str, str] = {}
    if not definitions:
        return
    while True:
        for definition in definitions:
            series = await _safe_call(
                app,
                stream="indicator",
                target_topic=topic,
                function=definition.name,
                params={
                    "symbol": definition.symbol,
                    "interval": definition.interval,
                    "time_period": definition.time_period,
                },
                coroutine=app.client.technicals.aget(
                    definition.name,
                    definition.symbol,
                    interval=definition.interval,
                    time_period=definition.time_period,
                    series_type=definition.series_type,
                ),
            )
            if series is None or not series.points:
                continue
            key = f"{definition.name}:{definition.symbol}:{definition.interval}"
            last_ts = seen.get(key)
            new_points = [p for p in series.points if not last_ts or p.timestamp > last_ts]
            if not new_points:
                continue
            for point in new_points:
                record = {
                    "ts_ns": to_epoch_ns(point.timestamp) or _now_ns(),
                    "symbol": definition.symbol,
                    "indicator": definition.name,
                    "interval": definition.interval,
                    "time_period": definition.time_period,
                    "series_type": definition.series_type,
                    "values": {k: v for k, v in point.values.items()},
                    "av_function": definition.name,
                    "ingest_ts_ns": _now_ns(),
                }
                app.publish(
                    stream="indicator",
                    topic=topic,
                    schema="alphavantage_indicator_v1",
                    record=record,
                    key=key,
                )
            seen[key] = max(p.timestamp for p in new_points)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Helpers + stream registry
# ---------------------------------------------------------------------------


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).rstrip("%"))
    except ValueError:
        return None


def _maybe_pct(value: Any) -> float | None:
    f = _maybe_float(value)
    return f


STREAMS: Dict[str, StreamRunner] = {
    "quote": quote_stream,
    "bar": bar_stream,
    "fx": fx_stream,
    "crypto": crypto_stream,
    "news": news_stream,
    "gainers": gainers_stream,
    "indicator": indicator_stream,
}


__all__ = [
    "STREAMS",
    "StreamRunner",
    "bar_stream",
    "crypto_stream",
    "fx_stream",
    "gainers_stream",
    "indicator_stream",
    "news_stream",
    "quote_stream",
]
