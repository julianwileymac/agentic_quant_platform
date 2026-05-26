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

Phase 3 §6.3 (RESTRUCTURING_PLAN.md) extension: the middleware also
stamps the current OTEL span with ``aqp.cell.id``, ``aqp.cell.region``,
``aqp.tenancy.strategy`` when the request's context carries cell
metadata (populated by the cell-router's ``X-AQP-Cell`` header).
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from aqp.tenancy.runtime_context import (
    reset_runtime_context,
    set_runtime_context,
)

logger = logging.getLogger(__name__)


def _stamp_cell_span_attributes(ctx: Any) -> None:
    """Add ``aqp.cell.*`` attributes to the current OTEL span.

    Phase 3 §6.3 — every request that traversed the cell-router
    carries ``cell_id`` / ``region`` / ``tenancy_strategy_alias`` on
    the :class:`RequestContext`. We propagate them to OTEL so traces
    in Tempo / Jaeger can be filtered by cell during incident
    response. The function is defensive: when OTEL is not installed,
    or when no cell metadata is present, it returns silently.
    """
    cell_id = getattr(ctx, "cell_id", None)
    region = getattr(ctx, "region", None)
    strategy_alias = getattr(ctx, "tenancy_strategy_alias", None)
    if not cell_id and not region and not strategy_alias:
        return
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if span is None:
        return
    try:
        if cell_id:
            span.set_attribute("aqp.cell.id", cell_id)
        if region:
            span.set_attribute("aqp.cell.region", region)
        if strategy_alias:
            span.set_attribute("aqp.tenancy.strategy", strategy_alias)
        # Mirror existing workspace / project attributes if present so
        # operators have a consistent set in Tempo / Jaeger.
        workspace_id = getattr(ctx, "workspace_id", None)
        project_id = getattr(ctx, "project_id", None)
        if workspace_id:
            span.set_attribute("aqp.workspace.id", workspace_id)
        if project_id:
            span.set_attribute("aqp.project.id", project_id)
    except Exception:  # noqa: BLE001 - defensive: OTEL errors must not break requests
        logger.debug("failed to stamp aqp.cell.* span attributes", exc_info=True)


class TenancyContextMiddleware(BaseHTTPMiddleware):
    """Bind ``request.state.aqp_context`` (if present) to the runtime contextvar."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        ctx = getattr(request.state, "aqp_context", None)
        token = set_runtime_context(ctx)
        if ctx is not None:
            _stamp_cell_span_attributes(ctx)
        try:
            response = await call_next(request)
        finally:
            reset_runtime_context(token)
        return response


__all__ = ["TenancyContextMiddleware"]
