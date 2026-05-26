"""TenancyStrategy ABC + self-registering metaclass (Workstream F).

Mirrors :class:`aqp.credentials.protocol.SecretStoreMeta` and
:class:`aqp.auth.providers.protocol.IdentityProviderMeta`. Subclasses
set ``strategy_kind`` (the dispatch key matched against
``Organization.tenancy_strategy``) and the metaclass calls
:func:`aqp.core.registry.register` automatically so introspection
endpoints can enumerate them without a manual decorator.

Lifecycle surface every strategy exposes:

- :meth:`session(org_id)` — async context manager yielding an
  AsyncSession bound to the right engine + isolation context for
  ``org_id``.
- :meth:`onboard(org_id, profile)` — provision whatever the strategy
  needs (the schema, the dedicated database, the per-tenant GUCs).
- :meth:`offboard(org_id)` — tear it back down.
- :meth:`describe()` — safe diagnostic surface (no DSNs, no GUC
  values).
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from typing import Any, AsyncContextManager, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


TENANCY_STRATEGY_KIND = "tenancy_strategy"


class TenancyStrategyError(Exception):
    """Base class for tenancy-strategy failures."""


class TenancyStrategyMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`TenancyStrategy` classes.

    Skips abstract bases (``__abstract_strategy__ = True`` or names
    starting with ``Base`` / ``_``).
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_strategy__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        kind = getattr(cls, "strategy_kind", None)
        if not kind:
            return cls
        alias = getattr(cls, "strategy_alias", None) or cls.__name__
        try:
            register(name=alias, kind=TENANCY_STRATEGY_KIND, source=str(kind))(cls)
        except Exception:  # noqa: BLE001
            logger.debug(
                "TenancyStrategy auto-registration failed for %s", name, exc_info=True
            )
        return cls


class TenancyStrategy(metaclass=TenancyStrategyMeta):
    """Pluggable per-organization isolation strategy.

    Subclasses set:

    - ``strategy_kind`` (``"shared_schema_rls"`` /
      ``"schema_per_tenant"`` / ``"database_per_enterprise"`` /
      ``"hybrid"``) — the dispatch key the factory matches against
      ``Organization.tenancy_strategy``.
    - ``strategy_alias`` (optional) — registry alias; defaults to the
      class name.
    """

    __abstract_strategy__: ClassVar[bool] = True

    strategy_kind: ClassVar[str] = ""
    strategy_alias: ClassVar[str | None] = None

    @abstractmethod
    def session(self, org_id: str | None) -> AsyncContextManager[Any]:
        """Return an async context manager yielding an AsyncSession.

        The returned session has the appropriate isolation context
        applied — for RLS strategies, the matching GUCs are set via
        ``SET LOCAL``; for schema-per-tenant, the ``search_path`` is
        pinned to the tenant schema + ``public_data``; for
        database-per-enterprise, the session is bound to the dedicated
        engine for that organisation.

        ``org_id`` may be ``None`` for system-level operations (migrations,
        background tasks scoped to no tenant); strategies decide whether
        to accept that — most accept it and yield a session against the
        canonical pool with no isolation context.
        """

    @abstractmethod
    async def onboard(self, org_id: str, profile: dict[str, Any]) -> None:
        """Provision whatever this strategy needs for a new tenant.

        For RLS this is a no-op (the row inserts itself once the
        organization is created). For schema-per-tenant this creates
        the schema and clones the template. For database-per-enterprise
        this creates the database + Vault namespace.
        """

    @abstractmethod
    async def offboard(self, org_id: str) -> None:
        """Tear down per-tenant resources after off-boarding.

        Strategies SHOULD soft-disable the tenant first (the
        Organization row is set to ``status="offboarded"`` upstream)
        and only delete physical resources after a documented retention
        window.
        """

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.strategy_kind,
            "alias": self.strategy_alias or self.__class__.__name__,
        }

    # ------------------------------------------------------------------
    # Phase 6 §9.4 — cell-aware engine accessors.
    #
    # Strategies that target the per-cell data plane override these to
    # return the cell's engine (looked up via ``RequestContext.cell_id``
    # → ``aqp/persistence/db.py``). The default implementations
    # delegate to the cluster-wide engine for backwards compatibility
    # with the shared-data-plane path.
    # ------------------------------------------------------------------

    def get_engine(self, org_id: str | None) -> Any:
        """Return the sync SQLAlchemy engine for ``org_id`` (Phase 6 §9.4).

        Default: delegates to ``aqp.persistence.db._sync_engine()``, which
        is cell-keyed. Strategies that need finer control (e.g.
        ``DatabasePerEnterpriseStrategy``) override this to return a
        dedicated engine.
        """
        from aqp.persistence.db import _sync_engine

        return _sync_engine()

    def get_async_engine(self, org_id: str | None) -> Any:
        """Return the async SQLAlchemy engine for ``org_id`` (Phase 6 §9.4).

        Default: delegates to ``aqp.persistence.db._async_engine()``.
        """
        from aqp.persistence.db import _async_engine

        return _async_engine()


def list_tenancy_strategy_classes() -> dict[str, type[TenancyStrategy]]:
    """Return ``{alias: class}`` for every registered tenancy strategy."""
    from aqp.core.registry import list_by_kind

    out: dict[str, type[TenancyStrategy]] = {}
    for alias, cls in list_by_kind(TENANCY_STRATEGY_KIND).items():
        if isinstance(cls, type) and issubclass(cls, TenancyStrategy):
            out[alias] = cls
    return out


__all__ = [
    "TENANCY_STRATEGY_KIND",
    "TenancyStrategy",
    "TenancyStrategyError",
    "TenancyStrategyMeta",
    "list_tenancy_strategy_classes",
]
