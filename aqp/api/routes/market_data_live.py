"""Live market-data subscriptions + WebSocket streaming.

``POST /live/subscribe`` spawns a background task that reads bars from a
concrete ``IMarketDataFeed`` (Alpaca / IBKR / simulated) and publishes
every bar onto ``aqp:live:<channel_id>`` via Redis pub/sub. Subscribing
clients connect to ``GET /live/stream/{channel_id}`` over WebSocket and
receive each bar as JSON.

The design mirrors ``/chat/stream/{task_id}`` (see
:mod:`aqp.api.routes.chat`) so the UI's existing WebSocket plumbing can
be reused verbatim.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, model_validator

from aqp.api.security import secure_router
from aqp.core.types import Symbol
from aqp.observability import get_tracer
from aqp.ws.broker import asubscribe, publish

logger = logging.getLogger(__name__)
tracer = get_tracer("aqp.live")
router = secure_router(prefix="/live", tags=["live-market"], default_scope="data:read")


# ---------------------------------------------------------------------------
# In-process channel registry
# ---------------------------------------------------------------------------


class _Subscription:
    def __init__(self, channel_id: str, venue: str, symbols: list[str]) -> None:
        self.channel_id = channel_id
        self.venue = venue
        self.symbols = symbols
        self.task: asyncio.Task[None] | None = None
        self.feed: Any | None = None


_SUBS: dict[str, _Subscription] = {}

# Most-recent payload reference price, keyed by ``(channel_id, vt_symbol)``.
# Populated by ``_feed_loop`` via :func:`_cache_reference_price` so
# ``GET /live/book`` can synthesise a sane mid price without a separate
# Redis read on every poll.
_LAST_PAYLOAD: dict[tuple[str, str], float] = {}


class SubscribeRequest(BaseModel):
    """Live-feed subscribe payload.

    Accepts both the legacy ``{venue, symbols}`` shape used by the
    Next.js webui and the simplified ``{vt_symbols}`` shape used by the
    Vite Live Trading Desk (``frontend/src/routes/live/page.tsx``).
    When the simplified shape is used, ``venue`` defaults to
    ``"simulated"`` so the desk works against the deterministic replay
    feed without forcing operators to choose a venue up front.
    """

    venue: str | None = Field(
        default=None,
        description="alpaca | ibkr | kafka | simulated. Defaults to 'simulated' when only vt_symbols is provided.",
    )
    symbols: list[str] | None = Field(
        default=None,
        description="Ticker strings (AAPL, SPY, ...) — legacy shape.",
    )
    vt_symbols: list[str] | None = Field(
        default=None,
        description="vt_symbols (AAPL.NASDAQ, ...) — frontend shape; aliased onto 'symbols'.",
    )
    poll_cadence_seconds: float = Field(default=5.0)
    kafka_topic: str | None = Field(
        default=None,
        description="Override the Kafka topic consumed when venue='kafka'. "
        "Defaults to features.normalized.v1.",
    )
    kafka_emit_as: str = Field(
        default="bar",
        description="bar | quote | tick | signal -- how KafkaDataFeed materializes "
        "records. Ignored for non-kafka venues.",
    )

    @model_validator(mode="after")
    def _normalize(self) -> "SubscribeRequest":
        if self.vt_symbols and not self.symbols:
            self.symbols = list(self.vt_symbols)
        if not self.venue:
            self.venue = "simulated"
        if not self.symbols:
            raise ValueError("at least one of symbols/vt_symbols must be provided")
        return self


class SubscribeResponse(BaseModel):
    channel_id: str
    venue: str
    symbols: list[str]
    stream_url: str


# ---------------------------------------------------------------------------
# Feed orchestrator
# ---------------------------------------------------------------------------


def _build_feed(
    venue: str,
    symbols: list[str],
    poll_cadence: float,
    *,
    kafka_topic: str | None = None,
    kafka_emit_as: str = "bar",
) -> Any:
    """Instantiate an ``IMarketDataFeed`` for ``venue``."""
    if venue == "simulated":
        import pandas as pd

        from aqp.trading.feeds.base import DeterministicReplayFeed

        # Synthetic bars for demo mode.
        now = pd.Timestamp.utcnow()
        rows = []
        for i in range(200):
            ts = now - pd.Timedelta(minutes=200 - i)
            for sym in symbols:
                base = 100 + (hash(sym) % 20)
                rows.append(
                    {
                        "timestamp": ts,
                        "vt_symbol": f"{sym}.SIM",
                        "open": base + i * 0.05,
                        "high": base + i * 0.06,
                        "low": base + i * 0.04,
                        "close": base + i * 0.05,
                        "volume": 1000 + i,
                    }
                )
        df = pd.DataFrame(rows)
        return DeterministicReplayFeed(df, cadence_seconds=poll_cadence, interval="1m")
    if venue == "alpaca":
        from aqp.trading.feeds.alpaca_feed import AlpacaDataFeed

        return AlpacaDataFeed()
    if venue == "ibkr":
        try:
            from aqp.trading.feeds.ibkr_feed import IBKRDataFeed
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "detail": str(exc),
                    "code": "dependency_missing",
                    "hint": 'Install IBKR support with: pip install -e ".[ibkr]"',
                },
            ) from exc

        return IBKRDataFeed()
    if venue == "kafka":
        # Consumes the Flink-processed stream (default
        # ``features.normalized.v1``) as the primary live venue. Falls back
        # to ``market.bar.v1`` if the caller opts for raw broker data.
        from aqp.trading.feeds.kafka_feed import KafkaDataFeed

        if kafka_emit_as not in {"bar", "quote", "tick", "signal"}:
            raise HTTPException(400, f"invalid kafka_emit_as: {kafka_emit_as!r}")
        return KafkaDataFeed(topic=kafka_topic, emit_as=kafka_emit_as)  # type: ignore[arg-type]
    raise HTTPException(404, f"unknown venue: {venue!r}")


def _error_payload(detail: str, *, code: str, hint: str) -> dict[str, str]:
    return {"detail": detail, "code": code, "hint": hint}


def _probe_ibkr_or_raise() -> None:
    from aqp.data.ibkr_historical import IBKRHistoricalService

    ok, message = IBKRHistoricalService.is_available(use_cache=False)
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=_error_payload(
                message,
                code="ibkr_unavailable",
                hint="Start TWS / IB Gateway and enable API socket access.",
            ),
        )


async def _feed_loop(sub: _Subscription) -> None:
    """Read events from the feed and relay them onto Redis ``aqp:live:*``."""
    feed = sub.feed
    if feed is None:
        return
    with tracer.start_as_current_span("live.feed_loop") as span:
        span.set_attribute("aqp.channel_id", sub.channel_id)
        span.set_attribute("aqp.venue", sub.venue)
        span.set_attribute("aqp.symbol_count", len(sub.symbols))
        if sub.symbols:
            span.set_attribute("aqp.symbols", ",".join(sub.symbols))
        first_published = False
        try:
            await feed.connect()
            logger.info(
                "live feed connected channel=%s venue=%s symbols=%s",
                sub.channel_id,
                sub.venue,
                ",".join(sub.symbols),
            )
            await feed.subscribe([Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in sub.symbols])
            logger.info(
                "live feed subscribed channel=%s venue=%s symbol_count=%d",
                sub.channel_id,
                sub.venue,
                len(sub.symbols),
            )
            async for event in feed.stream():
                payload = _event_to_payload(event)
                if payload is None:
                    continue
                # Cache the most-recent reference price so ``GET /live/book``
                # can synthesise a sane ladder without a Redis round-trip.
                _cache_reference_price(sub.channel_id, payload)
                try:
                    # ``publish`` is sync -- run in a worker thread and use the
                    # ``live`` namespace so it lands on ``aqp:live:<channel_id>``.
                    await asyncio.to_thread(publish, sub.channel_id, payload, namespace="live")
                    if not first_published:
                        first_published = True
                        span.add_event("live.first_payload_published")
                        logger.info(
                            "live first payload published channel=%s venue=%s kind=%s",
                            sub.channel_id,
                            sub.venue,
                            payload.get("kind"),
                        )
                except Exception as exc:
                    span.record_exception(exc)
                    logger.exception(
                        "live publish failed channel=%s venue=%s",
                        sub.channel_id,
                        sub.venue,
                    )
        except asyncio.CancelledError:
            span.add_event("live.feed_loop_cancelled")
            logger.info("live feed loop cancelled channel=%s", sub.channel_id)
            raise
        except Exception as exc:
            span.record_exception(exc)
            logger.exception("live feed loop error for %s", sub.channel_id)
        finally:
            with contextlib.suppress(Exception):
                await feed.disconnect()
            logger.info("live feed disconnected channel=%s venue=%s", sub.channel_id, sub.venue)
            # Ensure orphaned channel records don't linger if the loop dies
            # unexpectedly (e.g. provider connection failure).
            if _SUBS.get(sub.channel_id) is sub:
                _SUBS.pop(sub.channel_id, None)


def _event_to_payload(event: Any) -> dict[str, Any] | None:
    """Serialize a feed event (BarData, QuoteBar, TickData, Signal, dict) to JSON."""
    if event is None:
        return None
    # BarData has ``open/high/low/close/volume`` attrs; use that as the
    # primary discriminator so existing UI clients keep working.
    if hasattr(event, "open") and hasattr(event, "close"):
        return {
            "kind": "bar",
            "timestamp": str(event.timestamp),
            "vt_symbol": event.vt_symbol,
            "open": float(event.open),
            "high": float(event.high),
            "low": float(event.low),
            "close": float(event.close),
            "volume": float(event.volume),
        }
    if hasattr(event, "bid_close"):
        return {
            "kind": "quote",
            "timestamp": str(event.timestamp),
            "vt_symbol": event.vt_symbol,
            "bid_close": float(event.bid_close),
            "ask_close": float(event.ask_close),
            "bid_size": float(event.bid_size),
            "ask_size": float(event.ask_size),
        }
    if hasattr(event, "last"):
        return {
            "kind": "tick",
            "timestamp": str(event.timestamp),
            "vt_symbol": event.symbol.vt_symbol if hasattr(event, "symbol") else None,
            "bid": float(event.bid),
            "ask": float(event.ask),
            "last": float(event.last),
            "volume": float(event.volume),
        }
    if hasattr(event, "strength") and hasattr(event, "direction"):
        return {
            "kind": "signal",
            "timestamp": str(event.timestamp),
            "vt_symbol": event.symbol.vt_symbol if hasattr(event, "symbol") else None,
            "strength": float(event.strength),
            "direction": getattr(event.direction, "value", str(event.direction)),
            "confidence": float(event.confidence),
            "source": str(event.source),
        }
    if isinstance(event, dict):
        return event
    return None


def _cache_reference_price(channel_id: str, payload: dict[str, Any]) -> None:
    """Stash the latest reference price for a symbol on a channel.

    The synthesised order book in ``GET /live/book`` reads from this
    cache so the desk's depth ladder always centres around the most
    recent live tick.
    """
    vt = payload.get("vt_symbol")
    if not vt:
        return
    kind = payload.get("kind")
    price: float | None = None
    if kind == "bar":
        try:
            price = float(payload.get("close") or 0.0) or None
        except (TypeError, ValueError):
            price = None
    elif kind == "quote":
        try:
            bid = float(payload.get("bid_close") or 0.0)
            ask = float(payload.get("ask_close") or 0.0)
            if bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
        except (TypeError, ValueError):
            price = None
    elif kind == "tick":
        try:
            price = float(payload.get("last") or 0.0) or None
        except (TypeError, ValueError):
            price = None
    if price and price > 0:
        _LAST_PAYLOAD[(channel_id, str(vt))] = price


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(req: SubscribeRequest) -> SubscribeResponse:
    with tracer.start_as_current_span("live.subscribe") as span:
        span.set_attribute("aqp.venue", req.venue)
        span.set_attribute("aqp.symbol_count", len(req.symbols))
        if req.symbols:
            span.set_attribute("aqp.symbols", ",".join(req.symbols))
        if not req.symbols:
            raise HTTPException(400, "symbols must not be empty")
        if req.venue == "ibkr":
            _probe_ibkr_or_raise()
        channel_id = uuid.uuid4().hex[:12]
        span.set_attribute("aqp.channel_id", channel_id)
        try:
            feed = _build_feed(
                req.venue,
                req.symbols,
                req.poll_cadence_seconds,
                kafka_topic=req.kafka_topic,
                kafka_emit_as=req.kafka_emit_as,
            )
        except HTTPException as exc:
            span.record_exception(exc)
            raise
        except Exception as exc:
            span.record_exception(exc)
            raise HTTPException(
                status_code=502,
                detail=_error_payload(
                    f"Could not initialise {req.venue} live feed: {exc}",
                    code="subscribe_failed",
                    hint="Inspect API logs for feed startup failures.",
                ),
            ) from exc
        sub = _Subscription(channel_id=channel_id, venue=req.venue, symbols=list(req.symbols))
        sub.feed = feed
        sub.task = asyncio.create_task(_feed_loop(sub))
        _SUBS[channel_id] = sub
        logger.info(
            "live subscription created channel=%s venue=%s symbols=%s",
            channel_id,
            req.venue,
            ",".join(req.symbols),
        )
        return SubscribeResponse(
            channel_id=channel_id,
            venue=req.venue,
            symbols=req.symbols,
            stream_url=f"/live/stream/{channel_id}",
        )


@router.delete("/subscribe/{channel_id}")
async def unsubscribe(channel_id: str) -> dict[str, Any]:
    sub = _SUBS.pop(channel_id, None)
    if sub is None:
        raise HTTPException(404, f"no such channel: {channel_id!r}")
    if sub.task and not sub.task.done():
        logger.info("live unsubscribe requested channel=%s venue=%s", channel_id, sub.venue)
        sub.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sub.task
    logger.info("live subscription removed channel=%s venue=%s", channel_id, sub.venue)
    return {"channel_id": channel_id, "stopped": True}


@router.get("/subscriptions")
def list_subscriptions() -> list[dict[str, Any]]:
    return [
        {"channel_id": s.channel_id, "venue": s.venue, "symbols": s.symbols}
        for s in _SUBS.values()
    ]


# ---------------------------------------------------------------------------
# Frontend helpers — history bars + best-effort order book
# ---------------------------------------------------------------------------


@router.get("/history")
def history(vt_symbol: str, limit: int = 240, interval: str = "1d") -> list[dict[str, Any]]:
    """Return the most recent OHLC seed for a symbol.

    Used by ``frontend/src/routes/live/page.tsx`` to seed the WebGL OHLC
    chart before the live WebSocket starts emitting bars. The shape
    matches ``OhlcSeed`` in ``frontend/src/components/charts/OhlcChart.tsx``:
    ``{ time, open, high, low, close, volume? }`` with ``time`` as a unix
    second integer.
    """
    import datetime as _dt

    from aqp.core.types import DataNormalizationMode
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    if limit <= 0:
        return []

    try:
        sym = Symbol.parse(vt_symbol) if "." in vt_symbol else Symbol(ticker=vt_symbol)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid vt_symbol: {vt_symbol}") from exc

    end = _dt.datetime.utcnow()
    # Daily bars covering ~`limit` trading days; minute bars need a far
    # tighter window. Both modes ask for slightly more days than `limit`
    # to cover weekends / holidays and then trim at the tail.
    if interval == "1d":
        start = end - _dt.timedelta(days=int(limit * 1.6) + 7)
    else:
        start = end - _dt.timedelta(days=14)

    provider = DuckDBHistoryProvider()
    try:
        bars = provider.get_bars_normalized(
            [sym], start, end,
            interval=interval,
            normalization=DataNormalizationMode.ADJUSTED,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("history fetch failed for %s: %s", vt_symbol, exc)
        return []

    if bars is None or bars.empty:
        return []

    # The frame is multi-symbol but we asked for one. Sort by time and
    # tail to ``limit`` rows so the chart never blows up on huge ranges.
    bars = bars.sort_values("timestamp").tail(int(limit))
    out: list[dict[str, Any]] = []
    for _, row in bars.iterrows():
        ts = row.get("timestamp")
        if ts is None:
            continue
        try:
            unix_seconds = int(ts.timestamp()) if hasattr(ts, "timestamp") else int(ts)
        except Exception:  # noqa: BLE001
            continue
        out.append(
            {
                "time": unix_seconds,
                "open": float(row.get("open") or 0.0),
                "high": float(row.get("high") or 0.0),
                "low": float(row.get("low") or 0.0),
                "close": float(row.get("close") or 0.0),
                "volume": float(row.get("volume") or 0.0),
            }
        )
    return out


@router.get("/book")
def book(vt_symbol: str, depth: int = 10) -> dict[str, list[dict[str, float]]]:
    """Best-effort order book for a symbol.

    AQP's live feeds (Alpaca / IBKR / simulated / Kafka) do not expose
    L2 depth in the unified event stream; the WebSocket relay carries
    bars, quotes, ticks, and signals. So this endpoint synthesises a
    small symmetric book around the latest known mid price for the
    requested symbol when an active subscription has emitted at least
    one quote / tick / bar. When no reference is known, returns empty
    arrays — the frontend already polls every 1.5 s and degrades
    gracefully.

    Returned shape matches ``OrderBookLevel`` in
    ``frontend/src/components/live/OrderBook.tsx``:
    ``{ bids: [{ price, size, cumulative }], asks: [...] }``.
    """
    if depth <= 0:
        return {"bids": [], "asks": []}

    # Find the latest reference price published on any active subscription
    # that owns this symbol. ``aqp:live:<channel>`` payloads are JSON
    # blobs, so we keep a lightweight in-memory cache of the most-recent
    # quote per (channel_id, vt_symbol) keyed by ``_event_to_payload``.
    reference: float | None = None
    for sub in _SUBS.values():
        # Symbols may be tickers or vt_symbols; match either.
        if vt_symbol in sub.symbols or vt_symbol.split(".")[0] in sub.symbols:
            ref = _LAST_PAYLOAD.get((sub.channel_id, vt_symbol))
            if ref is None and "." in vt_symbol:
                ref = _LAST_PAYLOAD.get((sub.channel_id, vt_symbol.split(".")[0]))
            if ref is not None:
                reference = ref
                break

    if reference is None or reference <= 0:
        return {"bids": [], "asks": []}

    # Generate a synthetic book: 1 cent ladder, geometric size decay.
    bids: list[dict[str, float]] = []
    asks: list[dict[str, float]] = []
    cum_bid = 0.0
    cum_ask = 0.0
    for i in range(int(depth)):
        offset = (i + 1) * 0.01
        size = max(1.0, 1000.0 * (0.85 ** i))
        cum_bid += size
        cum_ask += size
        bids.append({"price": round(reference - offset, 4), "size": size, "cumulative": cum_bid})
        asks.append({"price": round(reference + offset, 4), "size": size, "cumulative": cum_ask})
    return {"bids": bids, "asks": asks}


@router.websocket("/stream/{channel_id}")
async def stream(ws: WebSocket, channel_id: str) -> None:
    """Relay Redis pub/sub messages for a live subscription to the client.

    Phase 3a authentication: first client frame must be
    ``{"type":"auth","token":"<JWT>"}``. See :mod:`aqp.auth.ws`.
    """
    from aqp.auth.ws import ws_authenticator

    await ws.accept()
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        return
    with tracer.start_as_current_span("live.ws.stream") as span:
        span.set_attribute("aqp.channel_id", channel_id)
        sub = _SUBS.get(channel_id)
        if sub is not None:
            span.set_attribute("aqp.venue", sub.venue)
            span.set_attribute("aqp.symbol_count", len(sub.symbols))
        if channel_id not in _SUBS:
            span.add_event("live.ws.unknown_channel")
            await ws.send_json({"error": f"no such channel: {channel_id}"})
            await ws.close()
            return
        logger.info("live ws relay connected channel=%s", channel_id)
        relayed = 0
        try:
            async for msg in asubscribe(channel_id, namespace="live"):
                await ws.send_json(msg)
                relayed += 1
                if relayed == 1:
                    span.add_event("live.ws.first_message")
                    logger.info("live ws first message channel=%s", channel_id)
        except WebSocketDisconnect:
            span.add_event("live.ws.client_disconnected")
        except Exception as exc:
            span.record_exception(exc)
            logger.exception("live ws error for %s", channel_id)
        finally:
            logger.info("live ws relay closed channel=%s messages=%d", channel_id, relayed)
