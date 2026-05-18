"""Tests for data-driven Iceberg namespace policy resolution."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.catalog.active_metadata import BusinessMetadata, register_dataset
from aqp.data.catalog.namespace_policy import (
    DEFAULT_POLICY,
    resolve_policy,
    validate_namespace_with_policy,
)
from aqp.metadata import write_aspect
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.models import Base, DatasetCatalog
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


@dataclass(slots=True)
class _RequestContext:
    workspace_id: str | None = None
    project_id: str | None = None
    user_id: str | None = "u-test"


@pytest.fixture
def namespace_policy_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite store and patch catalog session helpers."""
    from aqp.data.catalog import active_metadata as active_metadata_mod
    from aqp.data.catalog import namespace_policy as namespace_policy_mod

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            MetadataEntity.__table__,
            EntityAspect.__table__,
            DatasetCatalog.__table__,
        ],
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

    monkeypatch.setattr(namespace_policy_mod, "get_session", _patched_get_session)
    monkeypatch.setattr(active_metadata_mod, "get_session", _patched_get_session)
    return SessionLocal


def test_resolve_policy_without_scope_returns_default() -> None:
    """No scope uses hardcoded default medallion prefixes."""
    policy = resolve_policy(scope_urn=None)
    assert policy == DEFAULT_POLICY
    assert policy.source == "default"


def test_resolve_policy_nonexistent_scope_returns_default(namespace_policy_db: sessionmaker) -> None:
    """Unknown scope URNs fall back to default policy."""
    _ = namespace_policy_db
    policy = resolve_policy(scope_urn="urn:aqp:workspace:prod:nonexistent")
    assert policy == DEFAULT_POLICY
    assert policy.source == "default"


def test_resolve_policy_reads_written_aspect(namespace_policy_db: sessionmaker) -> None:
    """An icebergNamespacePolicy aspect overrides default prefixes."""
    scope_urn = "urn:aqp:workspace:prod:w1"
    with namespace_policy_db() as session:
        write_aspect(
            session,
            scope_urn,
            IcebergNamespacePolicy.aspect_name,
            IcebergNamespacePolicy(
                scope_urn=scope_urn,
                bronze_prefix="tenant_w1_bronze_",
                silver_prefix="tenant_w1_silver_",
                gold_prefix="tenant_w1_gold_",
                allowed_extra_prefixes=["tenant_w1_lab_"],
            ),
        )
        session.commit()

    policy = resolve_policy(scope_urn=scope_urn)
    assert policy.source == "aspect"
    assert policy.bronze_prefix == "tenant_w1_bronze_"
    assert policy.silver_prefix == "tenant_w1_silver_"
    assert policy.gold_prefix == "tenant_w1_gold_"
    assert "tenant_w1_lab_" in policy.allowed_extra_prefixes


def test_validate_namespace_with_policy_prefix_matching() -> None:
    """Bronze namespace must use bronze prefix when layer is declared."""
    validate_namespace_with_policy("bronze", "aqp_bronze_foo.bar")
    with pytest.raises(ValueError):
        validate_namespace_with_policy("bronze", "aqp_silver_foo.bar")


def test_validate_namespace_with_policy_rejects_reserved_namespace(
    namespace_policy_db: sessionmaker,
) -> None:
    """Reserved regulatory namespaces are forbidden even with explicit policy."""
    scope_urn = "urn:aqp:workspace:prod:w1"
    with namespace_policy_db() as session:
        write_aspect(
            session,
            scope_urn,
            IcebergNamespacePolicy.aspect_name,
            IcebergNamespacePolicy(scope_urn=scope_urn, forbidden_prefixes=[]),
        )
        session.commit()
    policy = resolve_policy(scope_urn=scope_urn)
    with pytest.raises(ValueError):
        validate_namespace_with_policy(None, "aqp_cfpb.complaints", policy=policy)


def test_iceberg_namespace_policy_rejects_invalid_prefix() -> None:
    """Invalid medallion prefixes should fail model validation."""
    with pytest.raises(ValidationError):
        IcebergNamespacePolicy(
            scope_urn="urn:aqp:workspace:prod:w1",
            bronze_prefix="aqp_bronze_",
            silver_prefix="bad-prefix",
            gold_prefix="aqp_gold_",
            forbidden_prefixes=[],
        )


def test_register_dataset_uses_workspace_policy(namespace_policy_db: sessionmaker) -> None:
    """register_dataset should honor per-workspace namespace policy overrides."""
    scope_urn = "urn:aqp:workspace:prod:w1"
    with namespace_policy_db() as session:
        write_aspect(
            session,
            scope_urn,
            IcebergNamespacePolicy.aspect_name,
            IcebergNamespacePolicy(
                scope_urn=scope_urn,
                silver_prefix="tenant_w1_silver_",
            ),
        )
        session.commit()

    result = register_dataset(
        "tenant_w1_silver_alpha_vantage.daily_bars",
        medallion_layer="silver",
        business_metadata=BusinessMetadata(
            data_owner="data-team",
            semantic_definition="Daily bars.",
        ),
        context=_RequestContext(workspace_id="w1"),
    )
    assert result.created is True

    with namespace_policy_db() as session:
        row = (
            session.execute(
                select(DatasetCatalog).where(
                    DatasetCatalog.iceberg_identifier
                    == "tenant_w1_silver_alpha_vantage.daily_bars"
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert row.medallion_layer == "silver"
