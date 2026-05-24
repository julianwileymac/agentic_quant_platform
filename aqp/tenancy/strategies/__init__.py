"""Concrete :class:`TenancyStrategy` implementations.

Importing this package transitively registers all four strategies via
:class:`TenancyStrategyMeta`. The factory in
:mod:`aqp.tenancy.factory` picks the right one per
:class:`Organization`.
"""
from __future__ import annotations

from aqp.tenancy.strategies.database_per_enterprise import (
    DatabasePerEnterpriseStrategy,
)
from aqp.tenancy.strategies.hybrid import HybridStrategy
from aqp.tenancy.strategies.schema_per_tenant import SchemaPerTenantStrategy
from aqp.tenancy.strategies.shared_schema_rls import SharedSchemaRLSStrategy

__all__ = [
    "DatabasePerEnterpriseStrategy",
    "HybridStrategy",
    "SchemaPerTenantStrategy",
    "SharedSchemaRLSStrategy",
]
