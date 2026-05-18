"""Tests for aspect.register_namespace_policy DataMCP tool."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools import aspects as aspects_tools
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite store and patch tool/session dependencies."""
    import aqp.metadata.namespace_policy as namespace_policy_mod

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

    monkeypatch.setattr(aspects_tools, "get_session", _patched_get_session)
    monkeypatch.setattr(namespace_policy_mod, "get_session", _patched_get_session)
    namespace_policy_mod.clear_policy_cache()
    try:
        yield SessionLocal
    finally:
        namespace_policy_mod.clear_policy_cache()


def _valid_policy_args() -> dict[str, object]:
    return {
        "urn": "urn:aqp:namespace_policy:prod:tool_acme",
        "policy_name": "Tool ACME policy",
        "bronze_prefix": "tool_bronze_",
        "silver_prefix": "tool_silver_",
        "gold_prefix": "tool_gold_",
        "applies_to_workspace_id": "W42",
        "priority": 25,
    }


def test_register_namespace_policy_tool_writes_aspect(aspect_db: sessionmaker) -> None:
    """Valid tool invocation writes an immutable namespace policy aspect."""
    tool = aspects_tools.RegisterNamespacePolicyTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read", "data:write")),
        **_valid_policy_args(),
    )
    assert result.ok is True
    assert result.data["urn"] == "urn:aqp:namespace_policy:prod:tool_acme"
    assert result.data["resolved_prefixes"]["bronze"] == "tool_bronze_"

    with aspect_db() as session:
        latest = session.execute(
            select(EntityAspect)
            .where(EntityAspect.urn == "urn:aqp:namespace_policy:prod:tool_acme")
            .where(EntityAspect.aspect_name == IcebergNamespacePolicy.aspect_name)
            .order_by(EntityAspect.version.desc())
            .limit(1)
        ).scalars().first()
        assert latest is not None


def test_register_namespace_policy_tool_invalid_prefix_returns_metadata_validation_error() -> None:
    """Invalid prefixes return a semantic MetadataValidationError payload."""
    tool = aspects_tools.RegisterNamespacePolicyTool()
    payload = _valid_policy_args()
    payload["bronze_prefix"] = "tool_bronze"
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read", "data:write")),
        **payload,
    )

    assert result.ok is False
    assert result.error == "MetadataValidationError"
    assert "bronze_prefix" in (result.metadata.get("fields") or [])


def test_register_namespace_policy_tool_respects_read_only_session() -> None:
    """Mutating namespace policy writes require the data:write scope."""
    tool = aspects_tools.RegisterNamespacePolicyTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        **_valid_policy_args(),
    )
    assert result.ok is False
    assert "policy denied" in (result.error or "").lower()
