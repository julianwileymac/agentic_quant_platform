"""Tests for paper baseline metadata aspect seeding."""
from __future__ import annotations

import pytest
from sqlalchemy import desc, select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
from aqp.trading.baseline_aspects import (
    BASELINE_PAPER_CONFIGS,
    seed_paper_baseline_aspects,
)


@pytest.fixture
def sqlite_session_factory() -> sessionmaker[Session]:
    """Create a hermetic in-memory sqlite metadata aspect store."""
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
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def test_seed_writes_baseline_aspects(sqlite_session_factory: sessionmaker[Session]) -> None:
    """First seed pass writes all five model and pipeline aspects."""
    with sqlite_session_factory() as session:
        result = seed_paper_baseline_aspects(session)
        session.commit()
    assert result == {"models_written": 5, "pipelines_written": 5}


def test_seed_is_idempotent(sqlite_session_factory: sessionmaker[Session]) -> None:
    """Second seed pass is a no-op via payload-hash dedup."""
    with sqlite_session_factory() as session:
        first = seed_paper_baseline_aspects(session)
        second = seed_paper_baseline_aspects(session)
        session.commit()
    assert first == {"models_written": 5, "pipelines_written": 5}
    assert second == {"models_written": 0, "pipelines_written": 0}


def test_seeded_models_are_production(sqlite_session_factory: sessionmaker[Session]) -> None:
    """Every seeded paper model URN resolves to Production status."""
    with sqlite_session_factory() as session:
        seed_paper_baseline_aspects(session)
        session.commit()
        for config in BASELINE_PAPER_CONFIGS:
            row = (
                session.execute(
                    select(EntityAspect)
                    .where(EntityAspect.urn == config.model_urn)
                    .where(EntityAspect.aspect_name == "mlModelMetadata")
                    .order_by(desc(EntityAspect.version), desc(EntityAspect.created_at))
                )
                .scalars()
                .first()
            )
            assert row is not None
            assert isinstance(row.payload, dict)
            assert row.payload.get("status") == "Production"
