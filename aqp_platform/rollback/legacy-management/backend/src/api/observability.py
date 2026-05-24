"""Observability deep-link + iframe-proxy endpoints.

The frontend's ``/monitoring`` page wants to embed Grafana, Jaeger, and Loki
inline so operators do not have to leave the management console.  Hard-coding
each service's hostname in the React app is fragile because it differs per
cluster install, so the backend is the single source of truth.

Two surfaces are exposed here:

* ``GET /api/observability/links`` - returns ``{name -> external URL}`` for
  each well-known dashboard.  The UI uses these as anchor / iframe ``src``
  values.
* ``GET /api/observability/iframe/{tool}`` - 302 redirect to the matching URL
  so the frontend can iframe a stable backend URL even if the underlying
  ingress host changes.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from ..config import Settings, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


# Mapping from short tool key to default ingress host.  Each entry is the
# *user-facing* URL (the URL a developer opens in their browser), not the
# in-cluster service DNS.
_DEFAULT_LINKS: dict[str, str] = {
    "grafana": "http://grafana.local",
    "jaeger": "http://jaeger.local",
    "loki": "http://loki.local",
    "prometheus": "http://prometheus.local",
    "datahub": "http://datahub.local",
    "mlflow": "http://mlflow.local",
    "minio": "http://minio.local",
    "argo": "http://argo.local",
    "dagster": "http://dagster.local",
    "flink": "http://flink.local",
    "schema-registry": "http://schema-registry.local",
    "jupyter": "http://jupyter.local",
    "milvus": "http://milvus.local",
    "vllm": "http://vllm.local",
}


def _resolve_links(settings: Settings) -> dict[str, str]:
    """Merge defaults with per-environment overrides."""

    overrides = getattr(settings, "observability_links", None) or {}
    return {**_DEFAULT_LINKS, **overrides}


@router.get("/links", response_model=dict[str, str])
async def get_dashboard_links(
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Return the full map of observability dashboard URLs."""

    return _resolve_links(settings)


@router.get("/links/{tool}", response_model=dict[str, str])
async def get_dashboard_link(
    tool: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Return the dashboard URL for a single tool key."""

    links = _resolve_links(settings)
    if tool not in links:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool}")
    return {"tool": tool, "url": links[tool]}


@router.get("/iframe/{tool}")
async def iframe_redirect(
    tool: str,
    path: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Stable backend URL that 302s to the resolved dashboard.

    Lets the frontend iframe a known URL like ``/api/observability/iframe/grafana``
    without baking the actual ingress host into the React build.
    """

    links = _resolve_links(settings)
    if tool not in links:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool}")
    target = links[tool]
    if path:
        target = target.rstrip("/") + "/" + path.lstrip("/")
    return RedirectResponse(url=target, status_code=302)
