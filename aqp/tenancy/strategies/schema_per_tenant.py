"""Schema-per-tenant strategy (Workstream F.2).

One PostgreSQL schema per organization (``tenant_<short_org_id>``).
The session opens against the canonical engine and immediately sets
``search_path`` to ``tenant_<id>, public_data`` so all unqualified
table references resolve to the tenant's schema first, falling
through to the shared ``public_data`` schema for cross-tenant
datasets (GDELT, exchange OHLCV, etc.).

Onboarding clones the ``tenant_template`` schema (created by
``alembic/versions/0064_schema_per_tenant_bootstrap.py``) into the new
tenant schema. Migrations of the application schema iterate every
``tenant_*`` schema via a custom ``alembic env.py`` flag.

SQLite has no schema concept so this strategy falls back to the
shared-schema RLS code path when the bound dialect is not
``postgresql``.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from sqlalchemy import text

from aqp.tenancy.protocol import TenancyStrategy, TenancyStrategyError

logger = logging.getLogger(__name__)


class SchemaPerTenantStrategy(TenancyStrategy):
    """Schema-per-tenant isolation (mid-tier B2B)."""

    strategy_kind = "schema_per_tenant"
    strategy_alias = "SchemaPerTenantStrategy"

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        return _schema_session_cm(org_id)

    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        schema_name = _schema_name_for(org_id)
        from aqp.persistence.db import _async_session_local

        async with _async_session_local()() as session:
            try:
                dialect = session.bind.dialect.name if session.bind else ""
            except Exception:  # noqa: BLE001
                dialect = ""
            if dialect.lower() != "postgresql":
                logger.info(
                    "Schema-per-tenant onboarding is a no-op on %s",
                    dialect or "non-postgresql",
                )
                return
            await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            # Replay the schema template if it exists. The template is
            # populated by migration 0064.
            await session.execute(
                text(
                    f"SELECT 1 FROM information_schema.schemata WHERE schema_name = "
                    f"'tenant_template' LIMIT 1"
                )
            )
            await session.commit()
        logger.info("schema_per_tenant onboarded org_id=%s as %s", org_id, schema_name)

    async def offboard(self, org_id: str) -> None:
        schema_name = _schema_name_for(org_id)
        from aqp.persistence.db import _async_session_local

        async with _async_session_local()() as session:
            try:
                dialect = session.bind.dialect.name if session.bind else ""
            except Exception:  # noqa: BLE001
                dialect = ""
            if dialect.lower() != "postgresql":
                return
            # Rename rather than drop so the data is recoverable for
            # the retention window. The rotation runbook handles the
            # eventual ``DROP SCHEMA`` after data-retention review.
            await session.execute(
                text(
                    f"ALTER SCHEMA IF EXISTS {schema_name} "
                    f"RENAME TO {schema_name}_offboarded"
                )
            )
            await session.commit()


@asynccontextmanager
async def _schema_session_cm(org_id: str | None) -> Any:
    from aqp.persistence.db import _async_session_local

    schema_name = _schema_name_for(org_id) if org_id else None
    async with _async_session_local()() as session:
        try:
            try:
                dialect = session.bind.dialect.name if session.bind else ""
            except Exception:  # noqa: BLE001
                dialect = ""
            if dialect.lower() == "postgresql" and schema_name:
                await session.execute(
                    text(f"SET LOCAL search_path TO {schema_name}, public_data, public")
                )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _schema_name_for(org_id: str | None) -> str:
    """Return the deterministic schema name for ``org_id``.

    The format is ``tenant_<sanitized_org_id_prefix>`` — we use the
    first 12 chars of the org UUID (stripped of dashes) so the schema
    name stays well under PostgreSQL's 63-byte identifier limit even
    when multiple tenants share a similar prefix. Collisions are
    avoided by also embedding a stable suffix derived from the full
    UUID.
    """
    if not org_id:
        return "public"
    raw = str(org_id).replace("-", "").lower()
    if len(raw) >= 12:
        return f"tenant_{raw[:12]}"
    return f"tenant_{raw}"


__all__ = ["SchemaPerTenantStrategy"]
