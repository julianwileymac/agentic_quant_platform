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
from pydantic import BaseModel, Field

from aqp.core.types import Symbol
from aqp.observability import get_tracer
from aqp.ws.broker import asubscribe, publish

logger = logging.getLogger(__name__)
tracer = get_tracer("aqp.live")
router = APIRouter(prefix="/live", tags=["live-market"])


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


class SubscribeRequest(BaseModel):
    venue: str = Field(..., description="alpaca | ibkr | kafka | simulated")
    symbols: list[str] = Field(..., description="Ticker strings (AAPL, SPY, ...)")
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


@router.websocket("/stream/{channel_id}")
async def stream(ws: WebSocket, channel_id: str) -> None:
    """Relay Redis pub/sub messages for a live subscription to the client."""
    await ws.accept()
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
