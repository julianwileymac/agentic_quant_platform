"""Health-probe endpoints (/healthz, /readyz, /metrics).

Used by the K8s livenessProbe + readinessProbe pod fields and by the
kube-prometheus-stack ServiceMonitor to scrape Prometheus metrics.

Returns a lightweight FastAPI app; the kernel mounts it on a side
channel (default port 9090) separate from the main bot traffic so
probes don't compete with the trading loop for the kernel thread.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def build_health_app(
    *,
    is_alive: Callable[[], bool] | None = None,
    is_ready: Callable[[], bool] | None = None,
) -> Any:
    """Build a minimal FastAPI app for health probes + metrics.

    ``is_alive`` defaults to always True (the process is up).
    ``is_ready`` defaults to always True (kernel reports its own
    readiness via kernel.fsm).

    The Prometheus ``/metrics`` endpoint uses the global
    :func:`prometheus_client.generate_latest` so any metrics produced
    by :class:`QuantBotMetrics` appear automatically.
    """
    try:
        from fastapi import FastAPI, Response
    except ImportError as exc:
        raise RuntimeError("FastAPI required for build_health_app") from exc

    app = FastAPI(title="QuantBot Health", version="0.2.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        if is_alive is not None and not is_alive():
            return {"status": "degraded"}
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        if is_ready is not None and not is_ready():
            return {"status": "not_ready"}
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics() -> Response:
        try:
            from prometheus_client import (  # type: ignore[import-not-found]
                CONTENT_TYPE_LATEST,
                generate_latest,
            )

            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except Exception:  # noqa: BLE001
            return Response(content=b"# prometheus_client unavailable\n", media_type="text/plain")

    return app


__all__ = ["build_health_app"]
