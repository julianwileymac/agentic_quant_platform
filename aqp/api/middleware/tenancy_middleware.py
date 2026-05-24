"""ASGI middleware that wires the tenancy runtime context (Workstream F).

For every request that passes :mod:`aqp.api.deps` auth, the active
:class:`RequestContext` is stashed into the
:mod:`aqp.tenancy.runtime_context` contextvar. Tenancy strategies read
the contextvar to derive the workspace id for ``SET LOCAL`` GUC
writes.

The middleware is intentionally minimal — it doesn't touch the
database or open a tenant session of its own. Routes that need a
tenant-scoped session reach for
:func:`aqp.tenancy.factory.get_tenancy_factory()` explicitly so we
don't pay the GUC roundtrip on every request (auth + cache hits skip
the session entirely).
"""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from aqp.tenancy.runtime_context import (
    reset_runtime_context,
    set_runtime_context,
)


class TenancyContextMiddleware(BaseHTTPMiddleware):
    """Bind ``request.state.aqp_context`` (if present) to the runtime contextvar."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        ctx = getattr(request.state, "aqp_context", None)
        token = set_runtime_context(ctx)
        try:
            response = await call_next(request)
        finally:
            reset_runtime_context(token)
        return response


__all__ = ["TenancyContextMiddleware"]
