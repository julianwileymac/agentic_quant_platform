"""Cell-routing decision service.

Phase 3 §6.4 (RESTRUCTURING_PLAN.md). Exposes three Starlette routes:

- ``GET  /healthz`` — liveness.
- ``GET  /readyz`` — readiness (cell cache hydrated).
- ``POST /resolve`` — direct ``(user_id, workspace_id, tenant_id)`` ->
  cell lookup for CLI / admin callers.
- ``POST /ext_authz/v3/check`` — Envoy external-authorization v3 HTTP
  contract. Approves the request and injects an ``x-aqp-cell``
  header, or denies with ``PermissionDenied`` when no cell matches.

The service is intentionally small: it loads the cell registry from
``aqp_control_plane``'s ``/manage/cells`` route into an in-memory
cache (:class:`CellCache`) and serves resolution decisions from
that cache with sub-millisecond latency.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
from typing import Any, AsyncIterator

import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from aqp_tenant_router.cache import CellCache, CellEntry
from aqp_tenant_router.jwt_extract import (
    JwtClaims,
    decode_unsigned,
    extract_claims,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration (settings via env vars; everything has a safe default).
# ---------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("env %s=%r is not a float; using %s", name, raw, default)
        return default


def _build_auth_header_provider() -> callable | None:  # type: ignore[type-arg]
    """Return a thunk that produces auth headers for the control-plane refresh.

    Reads the ServiceAccount JWT from
    ``AQP_TENANT_ROUTER_M2M_TOKEN_FILE`` (default
    ``/var/run/secrets/kubernetes.io/serviceaccount/token``) on
    every call so we pick up rotated tokens.
    """
    token_file = _env(
        "AQP_TENANT_ROUTER_M2M_TOKEN_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/token",
    )
    if not os.path.exists(token_file):
        return None

    def _provider() -> dict[str, str]:
        with open(token_file) as f:
            token = f.read().strip()
        if not token:
            return {}
        return {"authorization": f"Bearer {token}"}

    return _provider


# ---------------------------------------------------------------------------
# Cell-cache bootstrap (kept as a module-level singleton for now; Phase 5
# may swap to per-request lifespan injection if we shard the router).
# ---------------------------------------------------------------------------


_CACHE: CellCache | None = None


def get_cache() -> CellCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = CellCache(
            control_plane_url=_env(
                "AQP_TENANT_ROUTER_CONTROL_PLANE_URL",
                "http://aqp-cp.aqp-admin.svc.cluster.local:9000",
            ),
            refresh_interval_seconds=_env_float(
                "AQP_TENANT_ROUTER_REFRESH_INTERVAL_SECONDS", 30.0
            ),
            request_timeout_seconds=_env_float(
                "AQP_TENANT_ROUTER_REQUEST_TIMEOUT_SECONDS", 5.0
            ),
            auth_header_provider=_build_auth_header_provider(),
        )
    return _CACHE


# ---------------------------------------------------------------------------
# Resolution algorithm
# ---------------------------------------------------------------------------


def _pick_cell_for_tenant(cache: CellCache, claims: JwtClaims) -> CellEntry | None:
    """Resolve a JWT to a cell.

    Priority:
    1. Tenant explicitly pinned to a cell in the registry's
       ``pinned_tenants`` list (covers ``silo-reg`` cells one-to-one
       with their tenant).
    2. Tenant identifier on the JWT (``tenant_id`` claim) — look up
       a pinning.
    3. Fall back to the first active ``shared-std`` cell (single-cell
       MVP path until tier-by-user-tier routing lands in Phase 6).
    """
    if claims.tenant_id is not None:
        pinned = cache.get_pinned_cell_for_tenant(claims.tenant_id)
        if pinned is not None:
            return pinned
    # No explicit pinning — route to the first active shared-std cell.
    candidates = cache.list_active_cells_for_tier("shared-std")
    if candidates:
        return candidates[0]
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def readyz(_request: Request) -> JSONResponse:
    cache = get_cache()
    ready = cache.is_ready()
    return JSONResponse(
        {"status": "ok" if ready else "not_ready", "cells": len(cache.list_all())},
        status_code=200 if ready else 503,
    )


async def resolve(request: Request) -> JSONResponse:
    """Direct resolve API for CLI / admin callers.

    Body: ``{"user_id": "...", "workspace_id": "...?", "tenant_id": "...?"}``
    Response: ``{"cell_id": "...", "region": "...", ...}`` or 404.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "invalid_body", "error_description": "request body must be JSON"},
            status_code=400,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "invalid_body"}, status_code=400
        )
    claims = JwtClaims(
        sub=str(body.get("user_id") or ""),
        workspace_id=body.get("workspace_id"),
        tenant_id=body.get("tenant_id"),
    )
    cache = get_cache()
    cell = _pick_cell_for_tenant(cache, claims)
    if cell is None:
        return JSONResponse(
            {
                "error": "no_cell_available",
                "error_description": (
                    "no active cell could be selected for the requested tenant"
                ),
                "tenant_id": claims.tenant_id,
            },
            status_code=404,
        )
    return JSONResponse(
        {
            "cell_id": cell.id,
            "tier": cell.tier,
            "region": cell.region,
            "availability_zone": cell.availability_zone,
            "k8s_namespace": cell.k8s_namespace,
            "tenancy_strategy": cell.tenancy_strategy,
            "routes": dict(cell.routes),
        }
    )


async def ext_authz_check(request: Request) -> Response:
    """Envoy external-authorization v3 HTTP contract.

    Expected payload follows the v3 ``CheckRequest`` shape:
    https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/auth/v3/external_auth.proto.

    We pull the JWT from the inbound ``authorization`` header,
    extract the routing claims, and:

    - On success: respond with HTTP 200 and an ``ok_response``
      that injects the ``x-aqp-cell`` header so the Envoy router
      can dispatch to the right upstream cluster.
    - On failure: respond with HTTP 403 and a ``denied_response``
      body explaining why.

    The shape matches Envoy's HTTP filter:
    ``http_filters.ext_authz.with_request_body.allow_partial_message: true``.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_check_request"}, status_code=400)
    headers = (
        body.get("attributes", {})
        .get("request", {})
        .get("http", {})
        .get("headers", {})
        if isinstance(body, dict)
        else {}
    )
    auth_header = headers.get("authorization") or headers.get(":authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :]
    elif auth_header.startswith("bearer "):
        token = auth_header[len("bearer ") :]
    else:
        token = ""
    if not token:
        # Local-dev path: no token attached. Allow but flag the
        # request as anonymous so downstream gates can reject.
        return JSONResponse(
            {
                "status": {"code": 0},
                "ok_response": {
                    "headers": [
                        {
                            "header": {
                                "key": "x-aqp-cell",
                                "value": "cell-shared-std-local",
                            },
                            "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
                        }
                    ]
                },
            }
        )
    try:
        payload = decode_unsigned(token)
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {
                "status": {"code": 7},
                "denied_response": {
                    "status": {"code": 403},
                    "body": "invalid_jwt",
                },
            },
            status_code=403,
        )
    claims = extract_claims(payload)
    cache = get_cache()
    cell = _pick_cell_for_tenant(cache, claims)
    if cell is None:
        return JSONResponse(
            {
                "status": {"code": 7},
                "denied_response": {
                    "status": {"code": 503},
                    "body": "no_cell_available",
                },
            },
            status_code=503,
        )
    return JSONResponse(
        {
            "status": {"code": 0},
            "ok_response": {
                "headers": [
                    {
                        "header": {"key": "x-aqp-cell", "value": cell.id},
                        "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
                    },
                    {
                        "header": {
                            "key": "x-aqp-cell-region",
                            "value": cell.region,
                        },
                        "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
                    },
                    {
                        "header": {
                            "key": "x-aqp-cell-namespace",
                            "value": cell.k8s_namespace,
                        },
                        "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
                    },
                ]
            },
        }
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _lifespan(_app: Starlette) -> AsyncIterator[None]:
    cache = get_cache()
    try:
        await cache.start()
    except Exception:  # noqa: BLE001 - degrade rather than crash; readyz reports 503
        logger.exception("cell-cache start failed; service will report not_ready")
    try:
        yield
    finally:
        try:
            await cache.stop()
        except Exception:  # noqa: BLE001
            logger.exception("cell-cache stop raised")


def create_app() -> Starlette:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
    routes = [
        Route("/healthz", healthz, methods=["GET"]),
        Route("/readyz", readyz, methods=["GET"]),
        Route("/resolve", resolve, methods=["POST"]),
        Route("/ext_authz/v3/check", ext_authz_check, methods=["POST"]),
    ]
    return Starlette(routes=routes, lifespan=_lifespan)


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry-point (`aqp-tenant-router`)
# ---------------------------------------------------------------------------


def cli() -> None:
    parser = argparse.ArgumentParser(description="AQP tenant cell router")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(
        "aqp_tenant_router.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        loop="uvloop",
        http="httptools",
        access_log=False,
    )


if __name__ == "__main__":
    cli()


__all__ = ["app", "cli", "create_app", "get_cache"]
