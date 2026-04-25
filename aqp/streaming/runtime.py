"""Runtime glue for the ``aqp-stream-ingest`` entrypoint.

Spawns the requested ingesters, runs a tiny ``aiohttp`` health/metrics
server, and gracefully shuts everything down on SIGINT/SIGTERM.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from aqp.config import settings
from aqp.streaming.ingesters.base import BaseIngester
from aqp.streaming.kafka_producer import KafkaAvroProducer

logger = logging.getLogger(__name__)

Venue = str  # "ibkr" | "alpaca" | "all"


async def _serve_metrics(port: int) -> asyncio.AbstractServer | None:
    """Expose ``/metrics`` (prometheus) and ``/healthz`` on ``port``.

    Returns ``None`` if aiohttp or prometheus_client are missing so the
    ingester still runs -- just without HTTP introspection.
    """
    try:
        from aiohttp import web  # type: ignore[import]
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # type: ignore[import]
    except ImportError:  # pragma: no cover - optional deps
        logger.warning("aiohttp / prometheus_client missing; skipping metrics server")
        return None

    async def metrics_handler(_: Any) -> Any:
        return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)

    async def health_handler(_: Any) -> Any:
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/healthz", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("metrics/health server listening on :%d", port)

    # Return the runner so the caller can close it.
    return runner  # type: ignore[return-value]


def _build_ingesters(
    venue: Venue,
    producer: KafkaAvroProducer,
    universe: list[str],
) -> list[BaseIngester]:
    out: list[BaseIngester] = []
    if venue in {"ibkr", "all"}:
        try:
            from aqp.streaming.ingesters.ibkr import IBKRIngester

            out.append(IBKRIngester(producer=producer, universe=universe))
        except Exception:
            logger.exception("failed to construct IBKRIngester")
            if venue == "ibkr":
                raise
    if venue in {"alpaca", "all"}:
        try:
            from aqp.streaming.ingesters.alpaca import AlpacaIngester

            out.append(AlpacaIngester(producer=producer, universe=universe))
        except Exception:
            logger.exception("failed to construct AlpacaIngester")
            if venue == "alpaca":
                raise
    if not out:
        raise RuntimeError(f"No ingesters built for venue={venue!r}")
    return out


async def run_ingester(
    venue: Venue = "all",
    *,
    universe: list[str] | None = None,
    metrics_port: int | None = None,
) -> None:
    """Top-level coroutine used by the CLI.

    Builds shared Kafka producer + ingesters for ``venue`` and awaits
    until SIGINT/SIGTERM.
    """
    effective_universe = universe or settings.stream_universe_list
    if not effective_universe:
        raise RuntimeError(
            "Streaming universe is empty. Set AQP_STREAM_UNIVERSE or AQP_DEFAULT_UNIVERSE."
        )

    producer = KafkaAvroProducer()
    ingesters = _build_ingesters(venue=venue, producer=producer, universe=effective_universe)
    logger.info(
        "starting %d ingester(s) venue=%s universe=%s",
        len(ingesters),
        venue,
        ",".join(effective_universe),
    )

    runner = await _serve_metrics(metrics_port or settings.stream_metrics_port)

    loop = asyncio.get_event_loop()
    stop_signal = asyncio.Event()

    def _signal_handler(*_: Any) -> None:
        logger.info("received termination signal; shutting down")
        stop_signal.set()
        for ing in ingesters:
            ing.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: _signal_handler())

    tasks = [asyncio.create_task(ing.run(), name=f"ingester:{ing.venue}") for ing in ingesters]
    try:
        await stop_signal.wait()
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        producer.close()
        if runner is not None:
            try:
                await runner.cleanup()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("metrics server shutdown failed")
        logger.info("ingester shutdown complete")
