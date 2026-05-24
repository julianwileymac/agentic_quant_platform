"""
RPi Kubernetes Cluster Management API

Main application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .api import api_router
from .auth import require_authenticated_mgmt
from .config import get_settings
from .telemetry import setup_telemetry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()

    if settings.telemetry.enabled:
        setup_telemetry(settings, app=app)
        logger.info("OpenTelemetry tracing enabled")

    logger.info(f"Starting {settings.cluster_name} Management API")

    yield

    logger.info("Shutting down Management API")
    try:
        from rpi_k8s_sdk.tracing import shutdown_tracing

        shutdown_tracing()
    except ImportError:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="RPi Kubernetes Cluster Management API",
        description="Management API for Raspberry Pi Kubernetes cluster",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware — credentials enabled only when the origin
    # allowlist is concrete. Using ``*`` with credentials trips the
    # browser CORS preflight; keep them mutually exclusive.
    cors_origins = settings.cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes — every route inherits the
    # ``require_authenticated_mgmt`` dep so the management plane
    # rejects unauthenticated traffic when ``APP_AUTH_PROVIDER`` is
    # set. When the env var is unset (``none``) the dep is a no-op.
    app.include_router(
        api_router,
        prefix="/api",
        dependencies=[Depends(require_authenticated_mgmt)],
    )

    # Mount Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
