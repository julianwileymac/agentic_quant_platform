"""Slim FastAPI entrypoint for the unified ``aqp-client`` Kubernetes image.

The full ``aqp.api.main`` module imports every API router (SQLAlchemy, Celery,
Iceberg, …). The client container is a static-file + reverse-proxy gateway only;
it must not pull the monolith API dependency tree.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp.api.client_routes import install_client_surfaces

logger = logging.getLogger(__name__)

# Client pods always run in gateway mode (see aqp_platform/deployments/kubernetes base).
os.environ.setdefault("AQP_CLIENT_MODE", "true")

app = FastAPI(title="aqp-client", version="0.3.0", docs_url=None, redoc_url=None)


def _cors_origins() -> list[str]:
    raw = os.environ.get("AQP_WEBUI_CORS_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [part.strip() for part in raw.split(",") if part.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Probe target for the aqp-client Deployment (no downstream deps)."""
    return {"status": "ok", "service": "aqp-client"}


@app.get("/livez", include_in_schema=False)
def livez() -> dict[str, str]:
    return {"status": "alive", "service": "aqp-client"}


@app.get("/readyz", include_in_schema=False)
def readyz() -> dict[str, str]:
    return {"status": "ready", "service": "aqp-client"}


install_client_surfaces(app)
