"""Composite tenancy strategy: route per-organization (Workstream F).

The hybrid strategy is the production default. It looks up
``Organization.tenancy_strategy`` and dispatches to the matching
concrete strategy. Operators flip the org-level column to migrate a
single tenant between models — e.g. a mid-tier customer ascending to
enterprise gets ``database_per_enterprise`` set on their org row, and
the next session lands on a dedicated cluster.

Lookups go through a tiny in-process cache so we don't issue a
``SELECT tenancy_strategy FROM organizations`` on every session
checkout; the cache TTL is short (30 s) so operators see the new
strategy within one TTL after they flip the column.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager

from aqp.tenancy.protocol import TenancyStrategy, TenancyStrategyError
from aqp.tenancy.strategies.database_per_enterprise import DatabasePerEnterpriseStrategy
from aqp.tenancy.strategies.schema_per_tenant import SchemaPerTenantStrategy
from aqp.tenancy.strategies.shared_schema_rls import SharedSchemaRLSStrategy

logger = logging.getLogger(__name__)


_STRATEGY_CACHE: dict[str, tuple[float, str]] = {}
_STRATEGY_LOCK = threading.RLock()
_STRATEGY_TTL_SECONDS = 30.0


def _settings_default() -> str:
    try:
        from aqp.config import settings

        raw = str(
            getattr(settings, "tenancy_default_strategy", "shared_schema_rls") or "shared_schema_rls"
        )
        return raw.lower()
    except Exception:  # noqa: BLE001
        return "shared_schema_rls"


class HybridStrategy(TenancyStrategy):
    """Composite strategy that routes per-organization."""

    strategy_kind = "hybrid"
    strategy_alias = "HybridStrategy"

    def __init__(self) -> None:
        self._rls = SharedSchemaRLSStrategy()
        self._schema = SchemaPerTenantStrategy()
        self._db = DatabasePerEnterpriseStrategy()

    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        return _hybrid_session_cm(self, org_id)

    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        strategy = self._resolve_strategy_class(org_id)
        await strategy.onboard(org_id, profile)

    async def offboard(self, org_id: str) -> None:
        strategy = self._resolve_strategy_class(org_id)
        await strategy.offboard(org_id)

    # ------------------------------------------------------------------
    # Internal: resolve org -> concrete strategy
    # ------------------------------------------------------------------

    def _resolve_strategy_class(self, org_id: str | None) -> TenancyStrategy:
        kind = _lookup_org_strategy(org_id) if org_id else _settings_default()
        if kind == "database_per_enterprise":
            return self._db
        if kind == "schema_per_tenant":
            return self._schema
        return self._rls


def _lookup_org_strategy(org_id: str | None) -> str:
    """Return the configured strategy kind for ``org_id``, cached."""
    if not org_id:
        return _settings_default()
    key = str(org_id)
    now = time.monotonic()
    with _STRATEGY_LOCK:
        cached = _STRATEGY_CACHE.get(key)
        if cached is not None:
            expires_at, value = cached
            if now < expires_at:
                return value

    value = _settings_default()
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Organization

        with get_session() as session:
            org = (
                session.query(Organization)
                .filter(Organization.id == key)
                .one_or_none()
            )
            if org is not None:
                strat = getattr(org, "tenancy_strategy", None)
                if strat:
                    value = str(strat).lower()
    except Exception:  # noqa: BLE001
        # Fall back to the default when the table doesn't yet have the
        # column (migration 0063 hasn't been applied) or any other
        # transient error.
        logger.debug("strategy lookup fallback for org_id=%s", org_id, exc_info=True)

    with _STRATEGY_LOCK:
        _STRATEGY_CACHE[key] = (now + _STRATEGY_TTL_SECONDS, value)
    return value


@asynccontextmanager
async def _hybrid_session_cm(strategy: HybridStrategy, org_id: str | None) -> Any:
    concrete = strategy._resolve_strategy_class(org_id)
    async with concrete.session(org_id) as session:
        yield session


def reset_strategy_cache() -> None:
    """Drop the org->strategy cache (used by tests + after admin flips)."""
    with _STRATEGY_LOCK:
        _STRATEGY_CACHE.clear()


__all__ = ["HybridStrategy", "reset_strategy_cache"]
