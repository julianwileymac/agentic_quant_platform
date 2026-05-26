"""Shared-schema PostgreSQL RLS strategy (Workstream F.1).

This is the B2C default and the lowest-overhead isolation model. The
strategy opens an :class:`AsyncSession` against the canonical
:data:`async_engine` and immediately issues

    SET LOCAL app.current_organization_id = :org_id;
    SET LOCAL app.current_workspace_id = :workspace_id;

so the PostgreSQL Row-Level Security policies (defined by
``alembic/versions/0063_tenancy_strategy.py`` and the registry in
:mod:`aqp.tenancy.rls_policies`) reject cross-tenant SELECT / UPDATE /
DELETE / INSERT at the database layer.

SQLite test fixtures lack RLS support; the strategy detects that and
no-ops the GUC writes so the same code path keeps working in tests.
The cross-tenant isolation test suite (workstream F.1 acceptance
criterion) therefore requires the in-memory SQLite engine to be
swapped for a real PostgreSQL container; we expose a hermetic-safe
``set_session_context()`` helper for that case.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from sqlalchemy import text

from aqp.tenancy.protocol import TenancyStrategy, TenancyStrategyError

logger = logging.getLogger(__name__)


class SharedSchemaRLSStrategy(TenancyStrategy):
    """RLS-protected single-schema isolation."""

    strategy_kind = "shared_schema_rls"
    strategy_alias = "SharedSchemaRLSStrategy"

    def __init__(self) -> None:
        pass

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        """Yield an :class:`AsyncSession` with the RLS GUCs applied.

        ``org_id`` is the canonical organization UUID. Workspace id is
        inferred from the active :class:`RequestContext` when available
        (the ASGI middleware threads it through a ``contextvar``);
        callers that need to scope at the workspace level should
        ensure the context is populated before opening the session.
        """
        return _rls_session_cm(org_id)

    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        # RLS strategy onboarding is a no-op: the Organization row
        # inserts itself once application-level provisioning succeeds.
        # The migration already installed the policies on every table.
        logger.info("RLS onboard no-op for org_id=%s", org_id)

    async def offboard(self, org_id: str) -> None:
        # RLS offboarding is also a no-op at the strategy level —
        # rows belonging to the org stay readable by the BYPASSRLS
        # ``app_migrator`` role for the retention window before any
        # physical delete.
        logger.info("RLS offboard no-op for org_id=%s", org_id)


# ---------------------------------------------------------------------------
# Session context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _rls_session_cm(org_id: str | None) -> Any:
    from aqp.persistence.db import _async_session_local

    workspace_id = _current_workspace_id()
    cell_id = _current_cell_id()
    async with _async_session_local()() as session:
        try:
            await _set_session_context(
                session,
                org_id=org_id,
                workspace_id=workspace_id,
                cell_id=cell_id,
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _set_session_context(
    session: Any,
    *,
    org_id: str | None,
    workspace_id: str | None,
    cell_id: str | None = None,
) -> None:
    """Issue ``SET LOCAL`` for the GUCs the RLS policies reference.

    Phase 3 §6.3 — ``cell_id`` joins ``org_id`` and ``workspace_id`` as
    a tenancy GUC. The audit-log hash chain in Alembic 0083 reads
    ``NEW.cell_id``; per-cell RLS policies (Phase 6 §9.1) read
    ``current_setting('app.current_cell_id', true)``.

    On SQLite this is a no-op (SQLite doesn't recognise
    ``current_setting``). We detect the dialect from the bound engine
    and skip the writes when they aren't supported.
    """
    try:
        dialect = session.bind.dialect.name if session.bind else ""
    except Exception:  # noqa: BLE001
        dialect = ""
    if dialect and dialect.lower() != "postgresql":
        return
    if org_id:
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :v, true)"),
            {"v": str(org_id)},
        )
    if workspace_id:
        await session.execute(
            text("SELECT set_config('app.current_workspace_id', :v, true)"),
            {"v": str(workspace_id)},
        )
    if cell_id:
        await session.execute(
            text("SELECT set_config('app.current_cell_id', :v, true)"),
            {"v": str(cell_id)},
        )


def _current_workspace_id() -> str | None:
    """Read the workspace id from the active :class:`RequestContext`.

    The :mod:`aqp.auth.context` module stores the active context in a
    ``contextvars.ContextVar``; the ASGI middleware sets it for every
    request. We look it up defensively so the strategy works even when
    no context is active (background tasks, migrations, smoke scripts).
    """
    try:
        from aqp.tenancy.runtime_context import get_runtime_context

        ctx = get_runtime_context()
        if ctx is None:
            return None
        return getattr(ctx, "workspace_id", None)
    except Exception:  # noqa: BLE001
        return None


def _current_cell_id() -> str | None:
    """Read the cell id from the active :class:`RequestContext`.

    Phase 3 §6.3 — when the request arrived through the cell-router
    (``aqp-edge`` Envoy + ``aqp-tenant-router`` ext_authz callout) the
    middleware populates ``RequestContext.cell_id`` from the
    ``X-AQP-Cell`` header. Background tasks that didn't traverse the
    router (Celery workers, migrations, smoke scripts) get ``None``,
    which the strategy treats as the legacy single-cell path.
    """
    try:
        from aqp.tenancy.runtime_context import get_runtime_context

        ctx = get_runtime_context()
        if ctx is None:
            return None
        return getattr(ctx, "cell_id", None)
    except Exception:  # noqa: BLE001
        return None


__all__ = ["SharedSchemaRLSStrategy"]
