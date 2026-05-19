"""FastAPI middleware — Phase 4a control-plane maturation.

Two thin Starlette middlewares applied to the AQP API gateway in
:mod:`aqp.api.main`:

- :class:`CorrelationIDMiddleware` — read or generate an
  ``X-Request-ID`` header, bind it to :mod:`structlog`'s ``contextvars``
  so every log line tied to this request carries the same id, and echo
  it back to the client on the response. Pairs with the structured
  logging configuration in :func:`aqp.observability.logging.configure_structured_logging`
  to give operators a single id they can grep across services.
- :class:`StructuredLoggingMiddleware` — emit one structured
  ``http_request`` log line per request with method, path, status,
  duration, and client IP. The line is emitted AFTER the response is
  built so the status code + duration are accurate.

Middleware order matters: ``CorrelationIDMiddleware`` MUST be
registered BEFORE ``StructuredLoggingMiddleware`` so the id is bound
before the logging middleware records anything.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_REQUEST_ID_HEADER = "X-Request-ID"


def _bind_to_contextvars(**kwargs: Any) -> None:
    """Best-effort bind to structlog's contextvars.

    Soft-imports structlog so the middleware keeps working when
    structlog isn't installed (it just doesn't bind the field).
    """
    try:
        from structlog.contextvars import bind_contextvars

        bind_contextvars(**kwargs)
    except Exception:  # noqa: BLE001
        return


def _clear_contextvars() -> None:
    try:
        from structlog.contextvars import clear_contextvars

        clear_contextvars()
    except Exception:  # noqa: BLE001
        return


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Inject a per-request correlation id into logs + response headers.

    Reads ``X-Request-ID`` from the incoming request (set by an
    upstream load-balancer or proxy if present); generates a fresh
    UUID4 when absent. Binds it to ``structlog.contextvars`` so every
    log line emitted during the request carries the same id, and
    echoes it back on the response so clients can correlate their
    side of the call with the server-side log trail.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
        # Stash on request.state for handlers that want it without
        # re-reading the header.
        request.state.request_id = req_id

        _clear_contextvars()
        _bind_to_contextvars(request_id=req_id)

        try:
            response = await call_next(request)
        finally:
            # Don't leak the binding into the next request. Starlette
            # uses one task per request so this is essentially a
            # finally-on-task-end cleanup.
            _clear_contextvars()
        response.headers[_REQUEST_ID_HEADER] = req_id
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per HTTP request.

    Logs include method, path, status code, duration in milliseconds,
    client host, and any ``request_id`` bound by
    :class:`CorrelationIDMiddleware`. Uses ``aqp.observability.logging``
    so the line is JSON when structlog is installed and falls back to
    a stdlib record otherwise.

    Routes that are too noisy (``/livez``, ``/readyz``, ``/metrics``)
    are skipped to avoid flooding the log stream.
    """

    _SKIP_PATHS = frozenset({"/livez", "/readyz", "/metrics"})

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self._SKIP_PATHS:
            return await call_next(request)

        from aqp.observability.logging import get_logger

        logger = get_logger("aqp.api.http")
        start = time.perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
            client = request.client.host if request.client else "unknown"
            try:
                logger.info(
                    "http_request",
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client=client,
                )
            except Exception:  # noqa: BLE001
                # structlog absent / misconfigured → fallback to stdlib
                import logging

                logging.getLogger("aqp.api.http").info(
                    "http_request method=%s path=%s status=%s duration_ms=%s client=%s",
                    request.method,
                    path,
                    status_code,
                    duration_ms,
                    client,
                )


__all__ = [
    "CorrelationIDMiddleware",
    "StructuredLoggingMiddleware",
]
