"""Transparent HTTP reverse proxy for the unified ``aqp_client`` gateway.

When ``AQP_CLIENT_MODE=true`` (Phase 3 of the refactor) the FastAPI process
serves both the Vite SPA *and* proxies API calls to the backend services
addressed by :class:`aqp_platform_core.connectivity.ConnectivityConfig`.

Key invariants:

- Backend URLs are resolved AT REQUEST TIME, never at import time, so a pod
  rotation in K8s or a compose `up -d` doesn't require restarting the
  gateway.
- Response bodies stream (no full buffering) so large CSV / parquet
  downloads behave.
- The ``Host`` header is stripped + replaced with the upstream's host so
  hostname-based virtual hosting works.
- An M2M ``Authorization: Bearer <token>`` is injected on ``/manage/*``
  requests when the proxy is configured with a control-plane audience.
  The token cache lives in :mod:`aqp_platform_core.auth.jwt_validator`
  (issuer-side) and is fetched on demand.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator, Iterable

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.responses import StreamingResponse

from aqp_platform_core.connectivity import (
    ConnectivityConfig,
    get_connectivity_config,
)

logger = logging.getLogger(__name__)

# Headers that MUST NOT cross the proxy boundary. ``Host`` / ``Content-Length``
# are rewritten downstream; ``Connection`` / hop-by-hop headers are HTTP/1.1
# semantics that don't survive an httpx transport. ``Transfer-Encoding`` we
# rely on httpx + StreamingResponse to set correctly.
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
_STRIP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {"host", "content-length"}
_STRIP_RESPONSE_HEADERS = _HOP_BY_HOP_HEADERS | {"content-encoding", "content-length"}


# ---------------------------------------------------------------------------
# Shared httpx client
# ---------------------------------------------------------------------------


_client_singleton: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_http_client(config: ConnectivityConfig | None = None) -> httpx.AsyncClient:
    """Process-wide httpx client used for upstream calls.

    Created lazily so unit tests can substitute via :func:`set_http_client`.
    """
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    async with _client_lock:
        if _client_singleton is None:
            cfg = config or get_connectivity_config()
            _client_singleton = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=cfg.upstream_connect_timeout_seconds,
                    read=cfg.upstream_read_timeout_seconds,
                    write=cfg.upstream_read_timeout_seconds,
                    pool=cfg.upstream_connect_timeout_seconds,
                ),
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=20),
                follow_redirects=False,
                trust_env=False,
            )
    return _client_singleton


def set_http_client(client: httpx.AsyncClient) -> None:
    """Test helper — replace the proxy's httpx client."""
    global _client_singleton
    _client_singleton = client


async def close_http_client() -> None:
    """Release the proxy's httpx client (FastAPI shutdown hook)."""
    global _client_singleton
    if _client_singleton is not None:
        await _client_singleton.aclose()
        _client_singleton = None


# ---------------------------------------------------------------------------
# Header utilities
# ---------------------------------------------------------------------------


def _filter_request_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers
        if key.lower() not in _STRIP_REQUEST_HEADERS
    }


def _filter_response_headers(
    headers: Iterable[tuple[bytes | str, bytes | str]],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers:
        k = key.decode("latin-1") if isinstance(key, bytes) else key
        v = value.decode("latin-1") if isinstance(value, bytes) else value
        if k.lower() in _STRIP_RESPONSE_HEADERS:
            continue
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Core proxy function
# ---------------------------------------------------------------------------


async def proxy_request(
    *,
    request: Request,
    service: str,
    upstream_path: str,
    inject_authorization: str | None = None,
) -> Response:
    """Stream ``request`` upstream to ``service`` and return the response.

    ``upstream_path`` is appended to the service base URL (already includes
    a leading slash). ``inject_authorization``, when set, becomes the
    ``Authorization`` header on the upstream call — used by ``/manage/*``
    routes to attach an M2M token.
    """
    config = get_connectivity_config()
    try:
        route = config.route_for(service)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    target_url = f"{route.base_url}{upstream_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    headers = _filter_request_headers(request.headers.items())
    if inject_authorization:
        headers["authorization"] = inject_authorization

    # x-forwarded-* — preserve operator chain for downstream auth + logging.
    client_host = request.client.host if request.client else "127.0.0.1"
    headers.setdefault("x-forwarded-for", client_host)
    headers.setdefault("x-forwarded-proto", request.url.scheme)
    headers.setdefault("x-forwarded-host", request.url.netloc)
    headers["x-aqp-proxy-via"] = f"aqp-client/{route.source}"

    body = await request.body() if request.method not in {"GET", "HEAD"} else None

    client = await get_http_client(config)
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                target_url,
                headers=headers,
                content=body,
            ),
            stream=True,
        )
    except httpx.ConnectError as exc:
        logger.warning("proxy connect failed service=%s target=%s err=%s", service, target_url, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_unreachable",
                "service": service,
                "target": route.base_url,
                "source": route.source,
            },
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("proxy upstream error service=%s target=%s err=%s", service, target_url, exc)
        raise HTTPException(
            status_code=504,
            detail={
                "error": "upstream_timeout",
                "service": service,
                "target": route.base_url,
                "source": route.source,
            },
        ) from exc

    response_headers = _filter_response_headers(upstream.headers.raw)

    async def _aiter_body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        content=_aiter_body(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# Router factory — installed by aqp.api.main when AQP_CLIENT_MODE=true
# ---------------------------------------------------------------------------


def build_proxy_router() -> APIRouter:
    """Return an :class:`APIRouter` that proxies the standard service prefixes.

    Routes installed:

    - ``/api/*``     -> AQP core API
    - ``/ml/*``      -> AQP ML / testing API
    - ``/mcp/*``     -> DataMCP HTTP router
    - ``/manage/*``  -> aqp_control_plane (with optional M2M ``Authorization``)

    The Vite SPA at ``/`` and the Solara legacy UI at ``/legacy`` are NOT
    handled here — they live in :mod:`aqp.api.client_routes`.
    """
    router = APIRouter()

    # (connectivity_service_alias, public_url_prefix)
    _proxy_routes = (
        ("core", "/api"),
        ("ml", "/ml"),
        ("mcp", "/mcp"),
    )

    for service, prefix in _proxy_routes:

        @router.api_route(
            f"{prefix}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
            include_in_schema=False,
            name=f"proxy_{service}_root",
        )
        @router.api_route(
            f"{prefix}/{{path:path}}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
            include_in_schema=False,
            name=f"proxy_{service}_subpath",
        )
        async def _proxy(
            request: Request,
            path: str = "",
            _service: str = service,
            _prefix: str = prefix,
        ) -> Response:
            upstream_path = "/" + path if path else "/"
            return await proxy_request(
                request=request,
                service=_service,
                upstream_path=upstream_path,
            )

    # /manage/* — control plane proxy with optional M2M token injection.
    @router.api_route(
        "/manage",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
        name="proxy_manage_root",
    )
    @router.api_route(
        "/manage/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
        name="proxy_manage_subpath",
    )
    async def _proxy_manage(request: Request, path: str = "") -> Response:
        upstream_path = "/manage/" + path if path else "/manage/"
        # When the operator sets a M2M audience, mint a token via the
        # active IdentityProvider's client_credentials flow. We resolve
        # the credentials lazily to avoid a hard dep on aqp.auth at
        # gateway boot time.
        authorization = _request_m2m_token(request)
        return await proxy_request(
            request=request,
            service="control_plane",
            upstream_path=upstream_path,
            inject_authorization=authorization,
        )

    return router


def _request_m2m_token(request: Request) -> str | None:
    """Return ``Authorization: Bearer <token>`` for upstream control plane.

    Prefers an inbound user token (Bearer + valid JWT — already validated by
    the upstream control plane) when present; falls back to a server-minted
    M2M token via ``aqp.auth.m2m`` when ``AQP_CONTROL_PLANE_M2M_AUDIENCE``
    is set. Returns ``None`` when neither path is configured (dev mode).
    """
    inbound = request.headers.get("authorization")
    if inbound and inbound.lower().startswith("bearer "):
        return inbound

    audience = os.environ.get(
        "AQP_CONTROL_PLANE_M2M_AUDIENCE",
        "https://api.aqp.internal/manage",
    )
    if not audience:
        return None
    try:
        # Late import — aqp.auth.m2m pulls in CredentialResolver which is fine
        # at request time but heavy at gateway import time.
        from aqp.auth.m2m import mint_m2m_access_token

        token = mint_m2m_access_token(audience=audience)
    except Exception:  # noqa: BLE001
        # M2M not configured — drop through. The upstream control plane
        # will reject the request with 401 if it requires auth.
        return None
    return f"Bearer {token}" if token else None


__all__ = [
    "build_proxy_router",
    "close_http_client",
    "get_http_client",
    "proxy_request",
    "set_http_client",
]
