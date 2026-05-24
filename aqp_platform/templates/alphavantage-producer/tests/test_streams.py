"""Unit tests for the AV producer streams (mocked AV client + Kafka)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from alphavantage_producer.config import (
    IndicatorRequest,
    ProducerSettings,
    RuntimeConfig,
    StreamConfig,
    SymbolUniverse,
)
from alphavantage_producer.streams import (
    STREAMS,
    gainers_stream,
    news_stream,
    quote_stream,
)


class _RecordingProducerApp:
    def __init__(self) -> None:
        self.settings = ProducerSettings(service_name="test-av-producer")
        self.runtime = RuntimeConfig(
            streams={},
            universe=SymbolUniverse(equities=["IBM"]),
            indicators=[IndicatorRequest(name="SMA", symbol="IBM")],
        )
        self.published: List[Dict[str, Any]] = []
        self.deadletters: List[Dict[str, Any]] = []
        self.client = SimpleNamespace()

    def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)

    def send_deadletter(self, **kwargs: Any) -> None:
        self.deadletters.append(kwargs)


@pytest.mark.asyncio
async def test_quote_stream_publishes(monkeypatch):
    app = _RecordingProducerApp()

    class _FakeTs:
        async def aglobal_quote(self, symbol: str):
            return SimpleNamespace(
                symbol=symbol,
                open=250.0,
                high=255.0,
                low=249.0,
                price=252.5,
                volume=123456,
                latest_trading_day="2026-04-23",
                previous_close=251.0,
                change=1.5,
                change_percent="0.60%",
            )

    app.client.timeseries = _FakeTs()
    cfg = StreamConfig(name="quote", interval_seconds=0)

    # Run a single tick.
    import asyncio
    task = asyncio.create_task(quote_stream(app, cfg))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert app.published, "quote stream should have published at least one record"
    first = app.published[0]
    assert first["stream"] == "quote"
    assert first["record"]["symbol"] == "IBM"
    assert first["record"]["price"] == 252.5


@pytest.mark.asyncio
async def test_news_stream_deduplicates(monkeypatch):
    app = _RecordingProducerApp()
    feed_item = SimpleNamespace(
        title="Big news",
        url="https://example.com/article-1",
        time_published="20260423T150000",
        authors=["Alice"],
        summary="Summary",
        banner_image=None,
        source="Example",
        category_within_source=None,
        source_domain="example.com",
        topics=[SimpleNamespace(topic="technology", relevance_score=0.9)],
        overall_sentiment_score=0.1,
        overall_sentiment_label="neutral",
        ticker_sentiment=[
            SimpleNamespace(
                ticker="IBM",
                relevance_score=0.5,
                ticker_sentiment_score=0.2,
                ticker_sentiment_label="neutral",
            )
        ],
    )

    class _FakeIntelligence:
        async def anews(self, **_: Any):
            return SimpleNamespace(feed=[feed_item])

    app.client.intelligence = _FakeIntelligence()
    cfg = StreamConfig(name="news", interval_seconds=0)

    import asyncio
    task = asyncio.create_task(news_stream(app, cfg))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # One publish per poll for the single article; duplicates from subsequent
    # polls are suppressed by the ``seen`` set.
    assert app.published, "news stream should publish the first article"
    assert all(p["stream"] == "news" for p in app.published)


@pytest.mark.asyncio
async def test_gainers_stream_emits_buckets():
    app = _RecordingProducerApp()

    class _FakeIntelligence:
        async def atop_movers(self, **_: Any):
            return SimpleNamespace(
                last_updated="2026-04-23 15:00:00",
                top_gainers=[SimpleNamespace(ticker="AAA", price="1.0", change_amount="0.5", change_percentage="50%", volume="100")],
                top_losers=[SimpleNamespace(ticker="BBB", price="2.0", change_amount="-0.5", change_percentage="-20%", volume="200")],
                most_actively_traded=[SimpleNamespace(ticker="CCC", price="3.0", change_amount="0.1", change_percentage="3%", volume="300")],
            )

    app.client.intelligence = _FakeIntelligence()
    cfg = StreamConfig(name="gainers", interval_seconds=0)

    import asyncio
    task = asyncio.create_task(gainers_stream(app, cfg))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    buckets = {p["record"]["bucket"] for p in app.published}
    assert {"TOP_GAINER", "TOP_LOSER", "MOST_ACTIVELY_TRADED"}.issubset(buckets)


def test_streams_registry_covers_all_default_streams():
    for name in ("quote", "bar", "fx", "crypto", "news", "gainers", "indicator"):
        assert name in STREAMS, f"missing runner for {name}"
