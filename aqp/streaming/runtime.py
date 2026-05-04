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


def submit_factor_job(
    *,
    name: str,
    factor_expression: str | None = None,
    pipeline_export: dict[str, Any] | None = None,
    namespace: str | None = None,
    jar_uri: str | None = None,
    entry_class: str | None = None,
    args: list[str] | None = None,
    parallelism: int = 1,
) -> dict[str, Any]:
    """Submit a Flink session job that materialises an AQP factor / ML pipeline.

    Renders a :func:`aqp.streaming.templates.render_factor_session_job`
    manifest from the inputs and applies it via the kubernetes client
    wrapper in :mod:`aqp.streaming.admin.flink_admin`. This is the
    long-missing function referenced from
    :mod:`aqp.api.routes.factors` and :mod:`aqp.api.routes.ml`.

    Returns the rendered manifest's ``status`` once applied. Errors
    bubble out as :class:`aqp.streaming.admin.FlinkAdminError` so the
    caller can decide whether to fall back to the cluster-mgmt proxy.
    """
    from aqp.streaming.admin import (
        FlinkAdminError,
        FlinkAdminUnavailableError,
        get_flink_session_jobs,
    )
    from aqp.streaming.templates import render_factor_session_job

    ns = namespace or getattr(settings, "flink_namespace", None) or "default"
    jar = jar_uri or getattr(settings, "flink_factor_jar_uri", None) or "s3://flink-jobs/factor_compute.jar"
    entry = (
        entry_class
        or getattr(settings, "flink_factor_entry_class", None)
        or "io.aqp.flink.factor.FactorJob"
    )
    rendered_args: list[str] = list(args or [])
    if factor_expression and "--factor" not in rendered_args:
        rendered_args.extend(["--factor", str(factor_expression)])
    if pipeline_export and "--pipeline" not in rendered_args:
        rendered_args.extend(["--pipeline", str(pipeline_export)])

    manifest = render_factor_session_job(
        name=name,
        namespace=ns,
        factor_jar_uri=jar,
        entry_class=entry,
        args=rendered_args,
        parallelism=parallelism,
        state="running",
    )
    try:
        sessions = get_flink_session_jobs()
    except FlinkAdminUnavailableError:
        return {
            "status": "unavailable",
            "manifest": manifest,
            "message": "kubernetes client unavailable; manifest returned for manual apply",
        }
    try:
        existing = None
        try:
            existing = sessions.get(name, namespace=ns)
        except FlinkAdminError:
            existing = None
        if existing is None:
            applied = sessions.create(manifest)
            return {"status": "created", "session_job": applied.to_dict()}
        applied = sessions.patch(name, manifest, namespace=ns)
        return {"status": "patched", "session_job": applied.to_dict()}
    except FlinkAdminError as exc:
        return {"status": "error", "manifest": manifest, "message": str(exc)}
