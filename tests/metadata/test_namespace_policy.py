"""Tests for aspect-driven namespace policy resolution."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata.namespace_policy import (
    DEFAULT_PREFIXES,
    clear_policy_cache,
    register_namespace_policy,
    resolve_namespace_policy,
)
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


@pytest.fixture
def namespace_policy_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite store and patch resolver session access."""
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

    monkeypatch.setattr(namespace_policy_mod, "get_session", _patched_get_session)
    clear_policy_cache()
    try:
        yield SessionLocal
    finally:
        clear_policy_cache()


def _register(
    policy: IcebergNamespacePolicy,
    SessionLocal: sessionmaker,
) -> None:
    with SessionLocal() as session:
        register_namespace_policy(policy, session=session)
        session.commit()


def test_resolve_namespace_policy_defaults_without_aspects(namespace_policy_db: sessionmaker) -> None:
    """Resolver returns canonical defaults when no policy aspect exists."""
    _ = namespace_policy_db
    resolved = resolve_namespace_policy()
    assert resolved.source == "default"
    assert resolved.policy_urn is None
    assert resolved.bronze == DEFAULT_PREFIXES["bronze"]
    assert resolved.silver == DEFAULT_PREFIXES["silver"]
    assert resolved.gold == DEFAULT_PREFIXES["gold"]


def test_resolve_namespace_policy_global_override(namespace_policy_db: sessionmaker) -> None:
    """A global namespace policy overrides the canonical defaults."""
    _register(
        IcebergNamespacePolicy(
            urn="urn:aqp:namespace_policy:prod:global_default",
            policy_name="Global ACME policy",
            bronze_prefix="acme_bronze_",
            silver_prefix="acme_silver_",
            gold_prefix="acme_gold_",
            applies_to_workspace_id=None,
        ),
        namespace_policy_db,
    )
    resolved = resolve_namespace_policy()
    assert resolved.source == "aspect"
    assert resolved.bronze == "acme_bronze_"
    assert resolved.silver == "acme_silver_"
    assert resolved.gold == "acme_gold_"


def test_workspace_policy_beats_global_priority(namespace_policy_db: sessionmaker) -> None:
    """Higher-priority workspace policy wins over a global baseline."""
    _register(
        IcebergNamespacePolicy(
            urn="urn:aqp:namespace_policy:prod:global_policy",
            policy_name="Global",
            bronze_prefix="global_bronze_",
            silver_prefix="global_silver_",
            gold_prefix="global_gold_",
            priority=0,
        ),
        namespace_policy_db,
    )
    _register(
        IcebergNamespacePolicy(
            urn="urn:aqp:namespace_policy:prod:workspace_w42_policy",
            policy_name="Workspace W42",
            bronze_prefix="w42_bronze_",
            silver_prefix="w42_silver_",
            gold_prefix="w42_gold_",
            applies_to_workspace_id="W42",
            priority=10,
        ),
        namespace_policy_db,
    )

    resolved = resolve_namespace_policy(workspace_id="W42")
    assert resolved.bronze == "w42_bronze_"
    assert resolved.priority == 10


def test_domain_pattern_policy_matches_domain(namespace_policy_db: sessionmaker) -> None:
    """Domain-pattern policies only apply when the runtime domain matches."""
    _register(
        IcebergNamespacePolicy(
            urn="urn:aqp:namespace_policy:prod:domain_market_policy",
            policy_name="Market domain",
            bronze_prefix="market_bronze_",
            silver_prefix="market_silver_",
            gold_prefix="market_gold_",
            applies_to_domain_pattern=r"market\..*",
            priority=5,
        ),
        namespace_policy_db,
    )

    market = resolve_namespace_policy(domain="market.bars")
    other = resolve_namespace_policy(domain="fundamentals.statements")
    assert market.source == "aspect"
    assert market.bronze == "market_bronze_"
    assert other.source == "default"
    assert other.bronze == DEFAULT_PREFIXES["bronze"]


def test_register_namespace_policy_invalid_prefix_raises_validation_error() -> None:
    """Prefix validation requires a trailing underscore."""
    invalid_policy = IcebergNamespacePolicy.model_construct(
        urn="urn:aqp:namespace_policy:prod:bad_policy",
        policy_name="Bad",
        bronze_prefix="acme_bronze",
        silver_prefix="acme_silver_",
        gold_prefix="acme_gold_",
    )
    with pytest.raises(ValidationError):
        register_namespace_policy(invalid_policy)
