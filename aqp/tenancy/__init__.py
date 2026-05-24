"""Multi-tenant isolation strategies (Workstream F).

Three concrete strategies, all self-registering via
:class:`TenancyStrategyMeta`:

- :class:`SharedSchemaRLSStrategy` — PostgreSQL Row-Level Security on
  a shared schema (B2C default).
- :class:`SchemaPerTenantStrategy` — one PostgreSQL schema per
  organization (mid-tier B2B).
- :class:`DatabasePerEnterpriseStrategy` — dedicated PostgreSQL
  database per enterprise (regulated tier).

Plus :class:`HybridStrategy`, which composes the three above by
reading ``Organization.tenancy_strategy`` per request — the production
default.

Existing application-layer enforcement (RequestContext + Membership +
filter_resources_for_user) remains the outer ring; these strategies
add defense-in-depth underneath.
"""
from __future__ import annotations

from aqp.tenancy.factory import (
    TenancyStrategyFactory,
    get_tenancy_factory,
    reset_tenancy_factory,
)
from aqp.tenancy.protocol import (
    TENANCY_STRATEGY_KIND,
    TenancyStrategy,
    TenancyStrategyError,
    TenancyStrategyMeta,
    list_tenancy_strategy_classes,
)
from aqp.tenancy.strategies import (
    DatabasePerEnterpriseStrategy,
    HybridStrategy,
    SchemaPerTenantStrategy,
    SharedSchemaRLSStrategy,
)

__all__ = [
    "DatabasePerEnterpriseStrategy",
    "HybridStrategy",
    "SchemaPerTenantStrategy",
    "SharedSchemaRLSStrategy",
    "TENANCY_STRATEGY_KIND",
    "TenancyStrategy",
    "TenancyStrategyError",
    "TenancyStrategyFactory",
    "TenancyStrategyMeta",
    "get_tenancy_factory",
    "list_tenancy_strategy_classes",
    "reset_tenancy_factory",
]
