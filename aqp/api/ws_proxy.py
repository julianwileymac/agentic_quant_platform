"""WebSocket reverse proxy with exponential-backoff reconnect.

Pairs with :mod:`aqp.api.proxy` to provide the live + chat streams behind
the unified ``aqp_client`` gateway.

Behaviour per browser connection:

1. Accept the browser WebSocket immediately.
2. Open the upstream WebSocket (``websockets.connect``) addressed by
   :class:`aqp_platform_core.connectivity.ConnectivityConfig`.
3. Bidirectionally relay frames (browser <-> upstream) using two tasks.
4. On upstream disconnect, attempt to reconnect up to
   ``ConnectivityConfig.websocket_max_reconnect_attempts`` with
   exponential backoff (``websocket_reconnect_backoff_seconds *
   2**attempt``).
5. On final failure, close the browser connection with a structured
   ``CloseFrame(reason=...)`` so the client UI can show a meaningful
   "lost connection" toast.

The proxy is mounted only when ``AQP_CLIENT_MODE=true``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets
from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from aqp_platform_core.connectivity import (
    ConnectivityConfig,
    get_connectivity_config,
)

logger = logging.getLogger(__name__)

CLOSE_CODE_UPSTREAM_FAILURE = 1011  # internal error
CLOSE_CODE_UPSTREAM_EXHAUSTED = 4001  # operator should refresh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upstream_url(
    service: str,
    *,
    upstream_path: str,
    query_string: str = "",
    config: ConnectivityConfig | None = None,
) -> str:
    cfg = config or get_connectivity_config()
    route = cfg.route_for(service)
    base = route.base_url
    if base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    elif base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    url = f"{base}{upstream_path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url


async def _relay_browser_to_upstream(
    browser: WebSocket,
    upstream: websockets.WebSocketClientProtocol,
) -> None:
    try:
        while True:
            message = await browser.receive()
            mtype = message.get("type")
            if mtype == "websocket.disconnect":
                return
            if "text" in message and message["text"] is not None:
                await upstream.send(message["text"])
            elif "bytes" in message and message["bytes"] is not None:
                await upstream.send(message["bytes"])
    except WebSocketDisconnect:
        return
    except ConnectionClosed:
        return


async def _relay_upstream_to_browser(
    upstream: websockets.WebSocketClientProtocol,
    browser: WebSocket,
) -> None:
    try:
        async for frame in upstream:
            if isinstance(frame, bytes):
                await browser.send_bytes(frame)
            else:
                await browser.send_text(frame)
    except ConnectionClosed:
        return


# ---------------------------------------------------------------------------
# Reconnect loop
# ---------------------------------------------------------------------------


async def proxy_websocket(
    *,
    browser: WebSocket,
    service: str,
    upstream_path: str,
    forward_headers: Callable[[], dict[str, str]] | None = None,
) -> None:
    """Bidirectional WebSocket relay with reconnect-with-backoff.

    Accepts the browser WS itself, so callers just hand off the
    :class:`WebSocket` and the service/path.
    """
    cfg = get_connectivity_config()
    await browser.accept()

    max_attempts = max(0, int(cfg.websocket_max_reconnect_attempts))
    initial_backoff = max(0.0, float(cfg.websocket_reconnect_backoff_seconds))
    query_string = browser.scope.get("query_string", b"")
    query_string_str = (
        query_string.decode("ascii")
        if isinstance(query_string, (bytes, bytearray))
        else str(query_string or "")
    )

    attempt = 0
    while True:
        url = _upstream_url(
            service,
            upstream_path=upstream_path,
            query_string=query_string_str,
            config=cfg,
        )
        try:
            extra_headers = forward_headers() if forward_headers else {}
            async with websockets.connect(
                url,
                additional_headers=extra_headers or None,
                open_timeout=cfg.upstream_connect_timeout_seconds,
                close_timeout=5,
                max_size=None,
            ) as upstream:
                attempt = 0  # successful connection resets backoff
                tasks = [
                    asyncio.create_task(_relay_browser_to_upstream(browser, upstream)),
                    asyncio.create_task(_relay_upstream_to_browser(upstream, browser)),
                ]
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    try:
                        await task
                    except (asyncio.CancelledError, ConnectionClosed):
                        pass

                # If the browser side closed, we're done.
                browser_state = browser.application_state
                if str(browser_state) in {"WebSocketState.DISCONNECTED", "DISCONNECTED"}:
                    return
        except (ConnectionClosed, InvalidStatus, OSError, asyncio.TimeoutError) as exc:
            logger.warning(
                "ws_proxy upstream failure service=%s attempt=%d/%d err=%s",
                service,
                attempt,
                max_attempts,
                exc,
            )

        if attempt >= max_attempts:
            await _close_with_reason(
                browser,
                code=CLOSE_CODE_UPSTREAM_EXHAUSTED,
                reason=_structured_reason(
                    service=service,
                    detail="upstream_unreachable",
                    attempt=attempt,
                    max_attempts=max_attempts,
                ),
            )
            return

        backoff = initial_backoff * (2**attempt) if initial_backoff else 0
        attempt += 1
        if backoff:
            await asyncio.sleep(backoff)


async def _close_with_reason(
    browser: WebSocket, *, code: int, reason: str
) -> None:
    try:
        await browser.close(code=code, reason=reason)
    except RuntimeError:
        # Already closed / disconnected — best effort.
        return


def _structured_reason(
    *,
    service: str,
    detail: str,
    attempt: int,
    max_attempts: int,
) -> str:
    """Return a JSON-encoded reason short enough for a CloseFrame."""
    payload = json.dumps(
        {
            "service": service,
            "detail": detail,
            "attempt": attempt,
            "max_attempts": max_attempts,
        },
        separators=(",", ":"),
    )
    # WebSocket close reason max is 123 bytes (RFC 6455). Truncate JSON.
    if len(payload.encode("utf-8")) > 120:
        payload = payload[:120]
    return payload


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def build_websocket_proxy_router() -> APIRouter:
    """Return an :class:`APIRouter` exposing ``/ws/{service}/{path}``.

    Maps ``service`` to the connectivity config key. For Phase 3 we ship
    ``api`` and ``manage`` (control plane); future services slot in
    without touching this module.
    """
    router = APIRouter()

    @router.websocket("/ws/api/{path:path}")
    async def ws_api(websocket: WebSocket, path: str) -> None:
        # /ws/api/* -> the AQP core API's WebSocket surface.
        # Note: the connectivity service alias is "core" (matches
        # AQP_CORE_API_URL); the public URL prefix is /ws/api for
        # operator clarity and SPA convention.
        await proxy_websocket(
            browser=websocket,
            service="core",
            upstream_path=f"/ws/{path}",
        )

    @router.websocket("/ws/manage/{path:path}")
    async def ws_manage(websocket: WebSocket, path: str) -> None:
        await proxy_websocket(
            browser=websocket,
            service="control_plane",
            upstream_path=f"/manage/ws/{path}",
        )

    return router


__all__ = [
    "build_websocket_proxy_router",
    "proxy_websocket",
]
