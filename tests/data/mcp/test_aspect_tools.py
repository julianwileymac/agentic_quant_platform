"""Tests for Phase 3 metadata aspect DataMCP tools."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.config.defaults import DEFAULT_WORKSPACE_ID
from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools import aspects as aspects_tools
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

URN_A = "urn:aqp:dataset:prod:a"
URN_B = "urn:aqp:dataset:prod:b"
URN_C = "urn:aqp:dataset:prod:c"
MODEL_URN = "urn:aqp:mlmodel:prod:ridge_model_phase3"


def _hash_payload(payload: dict[str, Any]) -> str:
    """Return canonical payload hash compatible with ``write_aspect``."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seed_lineage_chain(SessionLocal: sessionmaker) -> None:
    """Seed A -> B -> C lineage edges with workspace=NULL visibility."""
    edge_ab = {
        "from_entity": URN_A,
        "to_entity": URN_B,
        "edge_type": "raw_to_table",
        "metadata": {"seed": "tests"},
    }
    edge_bc = {
        "from_entity": URN_B,
        "to_entity": URN_C,
        "edge_type": "table_to_feature",
        "metadata": {"seed": "tests"},
    }
    with SessionLocal() as session:
        session.execute(
            insert(MetadataEntity).values(
                urn=URN_A,
                entity_type="dataset",
                owner_user_id=None,
                workspace_id=None,
                project_id=None,
            )
        )
        session.execute(
            insert(MetadataEntity).values(
                urn=URN_B,
                entity_type="dataset",
                owner_user_id=None,
                workspace_id=None,
                project_id=None,
            )
        )
        session.execute(
            insert(EntityAspect).values(
                urn=URN_A,
                aspect_name="lineageEdge",
                version=1,
                payload=edge_ab,
                payload_hash=_hash_payload(edge_ab),
                system_metadata={},
                owner_user_id=None,
                workspace_id=None,
                project_id=None,
            )
        )
        session.execute(
            insert(EntityAspect).values(
                urn=URN_B,
                aspect_name="lineageEdge",
                version=1,
                payload=edge_bc,
                payload_hash=_hash_payload(edge_bc),
                system_metadata={},
                owner_user_id=None,
                workspace_id=None,
                project_id=None,
            )
        )
        session.commit()


def _valid_register_payload(*, model_version: str = "v1.0.0") -> dict[str, Any]:
    """Build a valid ``aspect.register_model`` payload."""
    return {
        "urn": MODEL_URN,
        "name": "Ridge Classifier Phase 3",
        "algorithm": "ridge",
        "ml_features": [
            {
                "name": "close_return_1d",
                "data_type": "numerical",
                "feature_sources": [
                    {
                        "source_urn": "urn:aqp:dataset:prod:aqp_silver_alpha_vantage.daily_bars",
                        "source_data_type": "float64",
                        "source_tags": ["price", "returns"],
                    }
                ],
                "feature_algorithm": "pct_change(close, 1)",
            }
        ],
        "ml_hyper_parameters": [
            {
                "name": "alpha",
                "value": "0.1",
                "value_type": "float",
                "description": "L2 penalty strength.",
            }
        ],
        "target": "forward_return_1d",
        "status": "Production",
        "model_version": model_version,
        "mlflow_run_id": "mlflow-run-42",
    }


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite store and patch ``get_session`` for tools."""
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
    _seed_lineage_chain(SessionLocal)

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
    return SessionLocal


def test_query_entity_lineage_walks_both_directions(aspect_db: sessionmaker) -> None:
    """Lineage query returns both upstream and downstream edges from focal B."""
    _ = aspect_db
    tool = aspects_tools.QueryEntityLineageTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        urn=URN_B,
        depth=2,
        direction="both",
    )

    assert result.ok is True
    assert result.rows_returned == 2
    data = result.data or {}
    upstream_pairs = {
        (edge["from_entity"], edge["to_entity"])
        for edge in data.get("upstream_edges", [])
    }
    downstream_pairs = {
        (edge["from_entity"], edge["to_entity"])
        for edge in data.get("downstream_edges", [])
    }
    assert (URN_A, URN_B) in upstream_pairs
    assert (URN_B, URN_C) in downstream_pairs


def test_register_model_returns_semantic_validation_payload_for_missing_target(
    aspect_db: sessionmaker,
) -> None:
    """Missing target surfaces MetadataValidationError with field guidance."""
    _ = aspect_db
    tool = aspects_tools.RegisterModelTool()
    payload = _valid_register_payload()
    payload.pop("target")

    result = tool.invoke(
        ctx=MCPToolContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            granted_scopes=("data:read", "data:write"),
        ),
        **payload,
    )

    assert result.ok is False
    assert result.error == "MetadataValidationError"
    assert "target" in (result.metadata.get("fields") or [])


def test_register_model_deduplicates_identical_payloads(aspect_db: sessionmaker) -> None:
    """Second write with the same payload reuses version and aspect_id."""
    _ = aspect_db
    tool = aspects_tools.RegisterModelTool()
    payload = _valid_register_payload(model_version="v1.0.0")
    ctx = MCPToolContext(
        workspace_id=DEFAULT_WORKSPACE_ID,
        granted_scopes=("data:read", "data:write"),
    )

    first = tool.invoke(ctx=ctx, **payload)
    second = tool.invoke(ctx=ctx, **payload)

    assert first.ok is True
    assert second.ok is True
    assert first.data["version"] == 1
    assert second.data["version"] == 1
    assert second.data["aspect_id"] == first.data["aspect_id"]


def test_register_model_bumps_version_when_payload_changes(aspect_db: sessionmaker) -> None:
    """Changed payload creates a new immutable aspect version."""
    _ = aspect_db
    tool = aspects_tools.RegisterModelTool()
    ctx = MCPToolContext(
        workspace_id=DEFAULT_WORKSPACE_ID,
        granted_scopes=("data:read", "data:write"),
    )

    first = tool.invoke(ctx=ctx, **_valid_register_payload(model_version="v1.0.0"))
    second = tool.invoke(ctx=ctx, **_valid_register_payload(model_version="v2.0.0"))

    assert first.ok is True
    assert second.ok is True
    assert second.data["version"] == 2


def test_get_aspect_history_returns_descending_versions(aspect_db: sessionmaker) -> None:
    """History query returns both model versions newest-first."""
    _ = aspect_db
    register = aspects_tools.RegisterModelTool()
    history = aspects_tools.GetAspectHistoryTool()
    ctx = MCPToolContext(
        workspace_id=DEFAULT_WORKSPACE_ID,
        granted_scopes=("data:read", "data:write"),
    )

    assert register.invoke(
        ctx=ctx,
        **_valid_register_payload(model_version="v1.0.0"),
    ).ok
    assert register.invoke(
        ctx=ctx,
        **_valid_register_payload(model_version="v2.0.0"),
    ).ok

    history_result = history.invoke(
        ctx=MCPToolContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            granted_scopes=("data:read",),
        ),
        urn=MODEL_URN,
        aspect_name="mlModelMetadata",
        limit=5,
    )
    assert history_result.ok is True
    versions = [row["version"] for row in history_result.data]
    assert versions[:2] == [2, 1]
    assert isinstance(history_result.data[0]["created_at"], str)


def test_register_model_scope_check_requires_data_write(aspect_db: sessionmaker) -> None:
    """Mutating model registration is denied when ``data:write`` is absent."""
    _ = aspect_db
    tool = aspects_tools.RegisterModelTool()
    result = tool.invoke(
        ctx=MCPToolContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            granted_scopes=("data:read",),
        ),
        **_valid_register_payload(model_version="v1.0.0"),
    )

    assert result.ok is False
    assert "policy denied" in (result.error or "").lower()
