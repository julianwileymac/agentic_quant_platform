"""Tests for active metadata namespace-policy integration."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.catalog.active_metadata import (
    BusinessMetadata,
    register_dataset,
    validate_layer_for_namespace,
)
from aqp.metadata import write_aspect
from aqp.metadata.namespace_policy import ResolvedPolicy, clear_policy_cache
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.models import Base, DatasetCatalog


@pytest.fixture
def active_metadata_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create an in-memory sqlite DB and patch metadata session accessors."""
    import aqp.data.catalog.active_metadata as active_metadata_mod
    import aqp.metadata.aspect_lookup as aspect_lookup_mod
    import aqp.metadata.namespace_policy as namespace_policy_mod

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
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

    monkeypatch.setattr(active_metadata_mod, "get_session", _patched_get_session)
    monkeypatch.setattr(namespace_policy_mod, "get_session", _patched_get_session)
    monkeypatch.setattr(aspect_lookup_mod, "get_session", _patched_get_session)
    clear_policy_cache()
    try:
        yield SessionLocal
    finally:
        clear_policy_cache()


def test_validate_layer_for_namespace_default_path() -> None:
    """Canonical prefixes still validate without any policy rows."""
    validate_layer_for_namespace("bronze", "aqp_bronze_foo")


def test_validate_layer_for_namespace_with_explicit_policy() -> None:
    """Explicit policy prefixes are honored during validation."""
    policy = ResolvedPolicy(
        bronze="acme_bronze_",
        silver="acme_silver_",
        gold="acme_gold_",
        policy_urn="urn:aqp:namespace_policy:prod:acme",
        priority=5,
        source="aspect",
    )
    validate_layer_for_namespace("bronze", "acme_bronze_foo", policy=policy)
    with pytest.raises(ValueError):
        validate_layer_for_namespace("bronze", "aqp_bronze_foo", policy=policy)


def test_register_dataset_supports_policy_urn(active_metadata_db: sessionmaker) -> None:
    """register_dataset keeps default behavior and supports policy_urn overrides."""
    bm = BusinessMetadata(
        data_owner="data-team",
        semantic_definition="Policy-aware ingestion dataset.",
        domain="market.bars",
    )

    baseline = register_dataset(
        "aqp_bronze_prices.daily",
        medallion_layer="bronze",
        business_metadata=bm,
        policy_urn=None,
    )
    assert baseline.created is True

    policy = IcebergNamespacePolicy(
        urn="urn:aqp:namespace_policy:prod:acme",
        policy_name="ACME namespace policy",
        bronze_prefix="acme_bronze_",
        silver_prefix="acme_silver_",
        gold_prefix="acme_gold_",
    )
    with active_metadata_db() as session:
        write_aspect(session, policy.urn, IcebergNamespacePolicy.aspect_name, policy)
        session.commit()

    policy_row = register_dataset(
        "acme_bronze_prices.daily",
        medallion_layer="bronze",
        business_metadata=bm,
        policy_urn="urn:aqp:namespace_policy:prod:acme",
    )
    assert policy_row.created is True

    with active_metadata_db() as session:
        row = session.execute(
            select(DatasetCatalog).where(
                DatasetCatalog.iceberg_identifier == "acme_bronze_prices.daily"
            )
        ).scalars().one()
        assert str((row.meta or {}).get("policy_urn")) == "urn:aqp:namespace_policy:prod:acme"
