"""FastAPI entrypoint for the internal admin surface.

Mounts three routers (health, accounts, services). Auth is enforced via
``Depends(require_admin)`` on every route except ``/admin/health``.

This module exposes a ``cli()`` console-script entry-point so the package
can be launched with ``aqp-admin-api`` after ``pip install``.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp_admin.api.routers import accounts, health, services
from aqp_admin.settings import get_settings

logger = logging.getLogger("aqp_admin")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    logger.info(
        "aqp_admin starting | api=%s control_plane=%s audit_sink=%s",
        settings.api_url,
        settings.control_plane_url,
        settings.audit_sink,
    )
    yield
    logger.info("aqp_admin stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AQP Admin",
        description="Internal admin surface for managed services + company accounts.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(services.router)
    return app


app = create_app()


def cli() -> None:
    """Console-script entrypoint registered in pyproject.toml."""
    uvicorn.run("aqp_admin.main:app", host="0.0.0.0", port=8900, reload=False)  # noqa: S104


if __name__ == "__main__":
    cli()
