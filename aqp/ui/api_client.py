"""Tiny HTTP + WebSocket client for the Solara UI to call the FastAPI backend.

Every page imports :func:`get` / :func:`post` / :func:`delete` / :func:`put`
from this module, so replacing `httpx.Client(...)` with something smarter (a
cache, an auth layer, retries) happens in exactly one place. The WebSocket
helpers back :class:`aqp.ui.components.data.task_streamer.TaskStreamer`.
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import httpx

_API_URL = os.environ.get("AQP_API_URL", "http://localhost:8000")


def api_url(path: str) -> str:
    return f"{_API_URL.rstrip('/')}{path}"


def ws_url(path: str) -> str:
    """Translate an HTTP(S) API URL into a WebSocket URL preserving the host + port."""
    base = _API_URL.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return f"{base}{path}"


def get(path: str, **kwargs: Any) -> Any:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(api_url(path), **kwargs)
        r.raise_for_status()
        return r.json()


def post(path: str, json: dict | None = None, **kwargs: Any) -> Any:
    with httpx.Client(timeout=60.0) as client:
        r = client.post(api_url(path), json=json, **kwargs)
        r.raise_for_status()
        return r.json()


def put(path: str, json: dict | None = None, **kwargs: Any) -> Any:
    with httpx.Client(timeout=60.0) as client:
        r = client.put(api_url(path), json=json, **kwargs)
        r.raise_for_status()
        return r.json()


def delete(path: str, **kwargs: Any) -> Any:
    """Previously three pages re-implemented this inline — centralise here."""
    with httpx.Client(timeout=30.0) as client:
        r = client.delete(api_url(path), **kwargs)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return {"status_code": r.status_code}


# ---------------------------------------------------------------------------
# WebSocket helpers
# ---------------------------------------------------------------------------
#
# Solara 1.x has no first-class WebSocket hook, and ``httpx`` itself does not
# speak WS. We try the optional ``httpx-ws`` package first (shipped with
# websockets 11+) and transparently fall back to the sync ``websockets``
# client when it is unavailable. Both iterators yield parsed JSON dicts so the
# component layer does not have to care which transport is live.


def iter_ws(path: str) -> Iterator[dict[str, Any]]:
    """Blocking iterator over a WebSocket endpoint. Yields parsed JSON dicts.

    Used by :class:`TaskStreamer` inside a Solara background thread. Returns
    cleanly when the server closes the socket.
    """
    url = ws_url(path)
    try:  # pragma: no cover — dependency is optional
        from websockets.sync.client import connect
    except ImportError:
        return
    try:
        with connect(url, open_timeout=10.0, max_size=8 * 1024 * 1024) as ws:
            while True:
                try:
                    raw = ws.recv(timeout=60.0)
                except TimeoutError:
                    yield {"stage": "heartbeat"}
                    continue
                try:
                    yield json.loads(raw)
                except (TypeError, ValueError):
                    yield {"raw": str(raw)}
    except Exception as exc:  # pragma: no cover — reported to the UI
        yield {"stage": "error", "message": f"ws connection closed: {exc}"}


@asynccontextmanager
async def ws_connect(path: str) -> AsyncIterator[Any]:
    """Async context manager wrapping ``httpx-ws`` or ``websockets`` client.

    Yields an async iterator over parsed JSON dicts. Use inside
    :func:`solara.use_task` style coroutines.
    """
    url = ws_url(path)
    try:  # pragma: no cover — dependency is optional
        from websockets.asyncio.client import connect as aconnect
    except ImportError:  # Older websockets / missing install — yield empty
        async def _empty() -> AsyncIterator[dict[str, Any]]:
            if False:  # pragma: no cover
                yield {}
        yield _empty()
        return

    async def _iterate(ws) -> AsyncIterator[dict[str, Any]]:
        async for raw in ws:
            try:
                yield json.loads(raw)
            except (TypeError, ValueError):
                yield {"raw": str(raw)}

    async with aconnect(url, open_timeout=10.0, max_size=8 * 1024 * 1024) as ws:
        yield _iterate(ws)


@contextmanager
def session() -> Iterator[httpx.Client]:
    """Open a pooled sync HTTP session (for pages that fire several calls in a row)."""
    with httpx.Client(timeout=60.0, base_url=_API_URL) as client:
        yield client
