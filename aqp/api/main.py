"""FastAPI gateway — the synchronous entry point for the UI and external clients.

This module also mounts the Dash visualization engine at ``/dash`` so the
whole platform is reachable from a single port.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp.api.routes import (
    agentic,
    agents,
    alpha_vantage,
    auth,
    backtest,
    brokers,
    chat,
    data,
    datalinks,
    entities,
    factors,
    feature_sets,
    fred,
    gdelt,
    health,
    identifiers,
    market_data_live,
    ml,
    paper,
    portfolio,
    registry,
    rl,
    sec,
    security,
    sources,
    strategies,
)
from aqp.config import settings
from aqp.observability import (
    configure_tracing,
    instrument_fastapi,
    shutdown_tracing,
)
from aqp.observability.tracing import instrument_httpx, instrument_redis

logger = logging.getLogger(__name__)


# Configure tracing at module import time (mirrors the Celery worker pattern)
# so every uvicorn worker — including the reloader child process — picks it up
# without relying on the lifespan hook, which doesn't fire consistently with
# --reload across uvicorn versions.
configure_tracing(service_name=f"{settings.otel_service_name}-api")
instrument_httpx()
instrument_redis()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AQP API starting | env=%s", settings.env)
    try:
        yield
    finally:
        logger.info("AQP API shutting down")
        shutdown_tracing()


app = FastAPI(
    title="Agentic Quant Platform API",
    version="0.2.0",
    description=(
        "Local-first quantitative research + trading API. Drives the agent crew, "
        "backtests, paper / live trading, RL training, and data ingestion. "
        "The Dash monitor is mounted at /dash."
    ),
    lifespan=lifespan,
)

# Attach FastAPI instrumentation immediately after app creation (before any
# middleware is added) so every route inherits request spans.
instrument_fastapi(app)

# CORS: when ``AQP_WEBUI_CORS_ORIGINS`` is set we restrict to that whitelist
# (production / shared hosts). Empty falls back to the legacy ``*`` so local
# Solara on :8765 and any direct callers keep working.
_cors_origins = settings.webui_cors_origin_list or ["*"]
_cors_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(agentic.router)
app.include_router(backtest.router)
app.include_router(rl.router)
app.include_router(data.router)
app.include_router(alpha_vantage.router)
app.include_router(portfolio.router)
app.include_router(paper.router)
app.include_router(brokers.router)
app.include_router(strategies.router)
app.include_router(registry.router)
app.include_router(feature_sets.router)
app.include_router(entities.router)
app.include_router(market_data_live.router)
app.include_router(factors.router)
app.include_router(ml.router)
app.include_router(security.router)
# Data-plane expansion routers (Phase 5 of the plan).
app.include_router(sources.router)
app.include_router(identifiers.router)
app.include_router(datalinks.router)
app.include_router(fred.router)
app.include_router(sec.router)
app.include_router(gdelt.router)


# ---------------------------------------------------------------------------
# Dash sub-app mount.
#
# Dash runs on Flask, which speaks WSGI; Starlette ships a WSGIMiddleware that
# adapts it to ASGI so the whole platform lives behind a single Uvicorn worker.
# The mount is best-effort: if Dash isn't installed (e.g. the paper-only
# container), we skip it without breaking the API.
# ---------------------------------------------------------------------------
def _mount_dash() -> None:
    """Try the modern ``a2wsgi`` adapter first, fall back to ``starlette``.

    Starlette's own ``WSGIMiddleware`` still works but is deprecated; their
    docs now point at ``a2wsgi`` which we treat as an optional speed-up.
    """
    try:
        from aqp.ui.dash_app import create_dash_app
    except Exception:  # pragma: no cover — dash not installed
        logger.warning("Dash not installed; /dash mount skipped", exc_info=True)
        return

    try:
        _dash_app = create_dash_app(requests_pathname_prefix="/dash/")
    except Exception:  # pragma: no cover
        logger.warning("Dash factory failed; /dash mount skipped", exc_info=True)
        return

    try:
        from a2wsgi import WSGIMiddleware  # type: ignore[import-not-found]
    except ImportError:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from starlette.middleware.wsgi import WSGIMiddleware  # type: ignore[assignment]

    app.mount("/dash", WSGIMiddleware(_dash_app.server))
    logger.info("Dash monitor mounted at /dash")


_mount_dash()


@app.get("/")
def root() -> dict:
    return {
        "app": "agentic-quant-platform",
        "version": "0.2.0",
        "docs": "/docs",
        "dash": "/dash/",
        "routes": [r.path for r in app.routes if hasattr(r, "path")],
    }
