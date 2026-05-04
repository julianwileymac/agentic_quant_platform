"""HTTP health probe for a Trino coordinator derived from ``AQP_TRINO_URI``."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


def trino_coordinator_http_url(*, sqlalchemy_uri: str | None = None) -> str:
    """Map ``trino://user@host:port/catalog`` to ``http://host:port`` for REST probes."""
    explicit = (settings.trino_http_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    uri = (sqlalchemy_uri or settings.trino_uri or "").strip()
    if not uri:
        return ""
    parsed = urlparse(uri)
    if parsed.scheme not in {"trino", "trinos"}:
        logger.warning("trino_uri scheme is %r; expected trino://", parsed.scheme)
        return ""
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    return f"http://{host}:{port}".rstrip("/")


def probe_trino_coordinator(*, timeout_seconds: float | None = None) -> dict[str, Any]:
    """GET ``/v1/info`` on the Trino coordinator. Never raises; returns ``ok`` + diagnostics."""
    timeout = float(timeout_seconds if timeout_seconds is not None else 5.0)
    base = trino_coordinator_http_url()
    out: dict[str, Any] = {
        "ok": False,
        "coordinator_url": base,
        "trino_uri": settings.trino_uri,
        "error": None,
        "node_id": None,
        "node_version": None,
    }
    if not base:
        out["error"] = "could not derive coordinator URL from AQP_TRINO_URI (or set AQP_TRINO_HTTP_URL)"
        return out
    url = f"{base}/v1/info"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        out["error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        return out
    except httpx.HTTPError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    except ValueError as exc:
        out["error"] = f"invalid JSON: {exc}"
        return out

    if not isinstance(payload, dict):
        out["error"] = "unexpected /v1/info payload shape"
        return out

    out["ok"] = True
    out["node_id"] = payload.get("nodeId")
    env = payload.get("environment")
    if isinstance(env, dict):
        out["node_version"] = env.get("nodeVersion") or env.get("javaVersion")
    return out


__all__ = ["probe_trino_coordinator", "trino_coordinator_http_url"]
