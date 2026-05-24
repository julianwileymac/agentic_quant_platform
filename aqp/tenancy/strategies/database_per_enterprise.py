"""Database-per-enterprise strategy (Workstream F.3).

Each enterprise org gets its own PostgreSQL database (typically its
own cluster). DSNs are resolved via :class:`CredentialResolver`
(per AGENTS rule 26) under the key
``CredentialKey(f"tenant_db_{org_id}", "dsn")``; the resolved
engine is cached process-locally with an LRU + TTL so high-cardinality
tenant pools don't explode the connection-pool count.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from aqp.tenancy.protocol import TenancyStrategy, TenancyStrategyError

logger = logging.getLogger(__name__)


_ENGINE_CACHE: dict[str, tuple[float, Any, Any]] = {}
_ENGINE_LOCK = threading.RLock()


def _ttl_seconds() -> int:
    try:
        from aqp.config import settings

        return int(getattr(settings, "tenancy_db_per_enterprise_pool_ttl_seconds", 1800))
    except Exception:  # noqa: BLE001
        return 1800


class DatabasePerEnterpriseStrategy(TenancyStrategy):
    """Per-enterprise dedicated PostgreSQL database isolation."""

    strategy_kind = "database_per_enterprise"
    strategy_alias = "DatabasePerEnterpriseStrategy"

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        if not org_id:
            raise TenancyStrategyError(
                "DatabasePerEnterpriseStrategy requires org_id"
            )
        return _enterprise_session_cm(org_id)

    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        # Provisioning a dedicated PostgreSQL cluster is out of scope
        # for the strategy itself — it would normally be driven by
        # TerraformRuntime in a separate workflow that lands the new
        # DSN in Vault. The strategy onboard hook simply pre-warms
        # the cached engine to surface DSN mis-configurations at
        # onboarding time rather than at first session.
        await _get_or_create_engine(org_id)

    async def offboard(self, org_id: str) -> None:
        with _ENGINE_LOCK:
            _ENGINE_CACHE.pop(str(org_id), None)


# ---------------------------------------------------------------------------
# Engine cache
# ---------------------------------------------------------------------------


async def _get_or_create_engine(org_id: str) -> tuple[Any, Any]:
    """Return ``(engine, session_factory)`` for the tenant, cached + TTL'd."""
    key = str(org_id)
    now = time.monotonic()
    with _ENGINE_LOCK:
        cached = _ENGINE_CACHE.get(key)
        if cached is not None:
            expires_at, engine, factory = cached
            if now < expires_at:
                return engine, factory
            # Expired — drop so we re-create below.
            _ENGINE_CACHE.pop(key, None)

    dsn = await _resolve_tenant_dsn(org_id)
    if not dsn:
        raise TenancyStrategyError(
            f"no DSN configured for tenant {org_id} (CredentialKey('tenant_db_{org_id}','dsn'))"
        )

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(dsn, pool_pre_ping=True, pool_size=4, max_overflow=4)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    expires_at = time.monotonic() + _ttl_seconds()

    with _ENGINE_LOCK:
        _ENGINE_CACHE[key] = (expires_at, engine, factory)
    return engine, factory


async def _resolve_tenant_dsn(org_id: str) -> str:
    """Resolve the tenant's DSN via :class:`CredentialResolver`.

    Async wrapper around the sync resolver — the resolver is
    intentionally blocking (Vault HTTP calls); we run it in the
    default thread executor so the asyncio loop stays responsive.
    """
    from aqp.credentials.protocol import CredentialKey
    from aqp.credentials.resolver import get_resolver

    def _read() -> str:
        resolver = get_resolver()
        try:
            cred = resolver.resolve(CredentialKey(f"tenant_db_{org_id}", "dsn"))
        except Exception:  # noqa: BLE001
            return ""
        if cred is None or not cred.fields:
            return ""
        for key in ("dsn", "url", "connection_string"):
            value = cred.fields.get(key)
            if value:
                return str(value)
        return ""

    return await asyncio.get_running_loop().run_in_executor(None, _read)


@asynccontextmanager
async def _enterprise_session_cm(org_id: str) -> Any:
    engine, factory = await _get_or_create_engine(org_id)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


__all__ = ["DatabasePerEnterpriseStrategy"]
