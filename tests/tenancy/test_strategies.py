"""TenancyStrategy registration + dispatch tests (Workstream F).

Covers the strategy abstraction without requiring a live PostgreSQL.
The cross-tenant isolation suite — which is the gate for declaring
F.1 done — needs a real Postgres container and lives separately under
:mod:`tests.tenancy.test_rls_isolation` (not exercised here so the
unit suite stays hermetic).
"""
from __future__ import annotations

import asyncio
import contextvars

import pytest


def test_metaclass_registers_all_four_strategies() -> None:
    from aqp.tenancy.protocol import list_tenancy_strategy_classes

    aliases = list_tenancy_strategy_classes()
    kinds = {str(getattr(cls, "strategy_kind", "")).lower() for cls in aliases.values()}
    assert "shared_schema_rls" in kinds
    assert "schema_per_tenant" in kinds
    assert "database_per_enterprise" in kinds
    assert "hybrid" in kinds


def test_factory_returns_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings
    from aqp.tenancy import (
        SharedSchemaRLSStrategy,
        get_tenancy_factory,
        reset_tenancy_factory,
    )

    monkeypatch.setattr(settings, "tenancy_default_strategy", "shared_schema_rls", raising=False)
    reset_tenancy_factory()

    factory = get_tenancy_factory()
    strategy = factory.default()
    assert isinstance(strategy, SharedSchemaRLSStrategy)


def test_factory_caches_strategies_per_kind() -> None:
    from aqp.tenancy import (
        SharedSchemaRLSStrategy,
        get_tenancy_factory,
        reset_tenancy_factory,
    )

    reset_tenancy_factory()
    factory = get_tenancy_factory()
    a = factory.for_kind("shared_schema_rls")
    b = factory.for_kind("shared_schema_rls")
    assert a is b
    assert isinstance(a, SharedSchemaRLSStrategy)


def test_hybrid_dispatch_falls_back_to_default_when_no_org() -> None:
    from aqp.tenancy import HybridStrategy

    strategy = HybridStrategy()
    concrete = strategy._resolve_strategy_class(None)
    # Default is shared_schema_rls.
    assert concrete.strategy_kind == "shared_schema_rls"


def test_runtime_context_propagates_through_asyncio_task() -> None:
    from aqp.tenancy.runtime_context import (
        get_runtime_context,
        set_runtime_context,
    )

    class _FakeCtx:
        workspace_id = "ws-1"

    async def _inner() -> str | None:
        ctx = get_runtime_context()
        return getattr(ctx, "workspace_id", None) if ctx is not None else None

    async def _outer() -> str | None:
        token = set_runtime_context(_FakeCtx())
        try:
            return await asyncio.create_task(_inner())
        finally:
            from aqp.tenancy.runtime_context import reset_runtime_context

            reset_runtime_context(token)

    result = asyncio.run(_outer())
    assert result == "ws-1"


def test_runtime_context_isolated_between_tasks() -> None:
    """Two concurrent tasks must not see each other's context."""
    from aqp.tenancy.runtime_context import (
        get_runtime_context,
        set_runtime_context,
    )

    class _FakeCtx:
        def __init__(self, workspace_id: str) -> None:
            self.workspace_id = workspace_id

    async def _task(workspace_id: str) -> str | None:
        ctx_obj = _FakeCtx(workspace_id)
        ctxvars_ctx = contextvars.copy_context()

        async def _body() -> str | None:
            token = set_runtime_context(ctx_obj)
            try:
                # Yield control so the other task interleaves here.
                await asyncio.sleep(0)
                got = get_runtime_context()
                return getattr(got, "workspace_id", None) if got is not None else None
            finally:
                from aqp.tenancy.runtime_context import reset_runtime_context

                reset_runtime_context(token)

        return await asyncio.create_task(_body())

    async def _both() -> tuple[str | None, str | None]:
        return await asyncio.gather(_task("alpha"), _task("beta"))

    a, b = asyncio.run(_both())
    assert {a, b} == {"alpha", "beta"}


def test_schema_per_tenant_schema_name_is_deterministic() -> None:
    from aqp.tenancy.strategies.schema_per_tenant import _schema_name_for

    org_id = "11111111-2222-3333-4444-555566667777"
    name = _schema_name_for(org_id)
    assert name.startswith("tenant_")
    # Length must stay within Postgres's 63-byte identifier limit.
    assert len(name) <= 63


def test_database_per_enterprise_requires_org_id() -> None:
    from aqp.tenancy import DatabasePerEnterpriseStrategy
    from aqp.tenancy.protocol import TenancyStrategyError

    strategy = DatabasePerEnterpriseStrategy()
    with pytest.raises(TenancyStrategyError):
        # Calling .session(None) returns a CM — entering it should raise.
        async def _check() -> None:
            async with strategy.session(None):
                pass

        asyncio.run(_check())
