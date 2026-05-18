"""Tests for iceberg.namespace_policy DataMCP tools."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.catalog import namespace_policy as namespace_policy_catalog
from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools import namespace_policy as namespace_policy_tools
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


@pytest.fixture
def namespace_policy_tool_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create an isolated sqlite DB and patch both tool + resolver sessions."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[MetadataEntity.__table__, EntityAspect.__table__],
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(namespace_policy_tools, "get_session", _patched_get_session)
    monkeypatch.setattr(namespace_policy_catalog, "get_session", _patched_get_session)
    return SessionLocal


def test_get_namespace_policy_tool_returns_default_when_missing(
    namespace_policy_tool_db: sessionmaker,
) -> None:
    """Get tool should return default prefixes when no aspect exists."""
    _ = namespace_policy_tool_db
    tool = namespace_policy_tools.GetNamespacePolicyTool()
    result = tool.invoke(
        ctx=MCPToolContext(workspace_id="w1", granted_scopes=("data:read",))
    )
    assert result.ok is True
    assert result.data["source"] == "default"
    assert result.data["bronze_prefix"] == "aqp_bronze_"
    assert result.data["silver_prefix"] == "aqp_silver_"
    assert result.data["gold_prefix"] == "aqp_gold_"


def test_set_then_get_namespace_policy_tool_round_trip(
    namespace_policy_tool_db: sessionmaker,
) -> None:
    """Set tool should persist an aspect that the get tool resolves."""
    _ = namespace_policy_tool_db
    scope_urn = "urn:aqp:workspace:prod:w1"
    set_tool = namespace_policy_tools.SetNamespacePolicyTool()
    get_tool = namespace_policy_tools.GetNamespacePolicyTool()

    set_result = set_tool.invoke(
        ctx=MCPToolContext(
            workspace_id="w1",
            granted_scopes=("data:read", "data:write"),
        ),
        scope_urn=scope_urn,
        bronze_prefix="tenant_w1_bronze_",
        silver_prefix="tenant_w1_silver_",
        gold_prefix="tenant_w1_gold_",
    )
    assert set_result.ok is True
    assert set_result.data["version"] == 1

    get_result = get_tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        scope_urn=scope_urn,
    )
    assert get_result.ok is True
    assert get_result.data["source"] == "aspect"
    assert get_result.data["bronze_prefix"] == "tenant_w1_bronze_"
    assert get_result.data["silver_prefix"] == "tenant_w1_silver_"
    assert get_result.data["gold_prefix"] == "tenant_w1_gold_"


def test_set_namespace_policy_tool_returns_validation_error_payload(
    namespace_policy_tool_db: sessionmaker,
) -> None:
    """Invalid prefixes should return MetadataValidationError payloads."""
    _ = namespace_policy_tool_db
    set_tool = namespace_policy_tools.SetNamespacePolicyTool()
    result = set_tool.invoke(
        ctx=MCPToolContext(
            workspace_id="w1",
            granted_scopes=("data:read", "data:write"),
        ),
        scope_urn="urn:aqp:workspace:prod:w1",
        silver_prefix="bad-prefix",
    )
    assert result.ok is False
    assert result.error == "MetadataValidationError"
    assert "silver_prefix" in (result.metadata.get("fields") or [])
