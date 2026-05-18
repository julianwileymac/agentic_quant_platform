"""Immutability guard tests for canonical metadata aspects."""
from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata.exceptions import ImmutableAspectError
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


@pytest.fixture
def aspect_session() -> tuple[sessionmaker, str]:
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
    payload = {"field": "value"}
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with SessionLocal() as session:
        entity = MetadataEntity(urn="urn:aqp:dataset:dev:test.table", entity_type="dataset")
        aspect = EntityAspect(
            urn=entity.urn,
            aspect_name="datasetProperties",
            version=1,
            payload=payload,
            payload_hash=payload_hash,
        )
        session.add(entity)
        session.add(aspect)
        session.commit()
        aspect_id = str(aspect.id)
    return SessionLocal, aspect_id


def test_bulk_update_raises_immutable_aspect_error(
    aspect_session: tuple[sessionmaker, str],
) -> None:
    SessionLocal, aspect_id = aspect_session
    with SessionLocal() as session:
        with pytest.raises(ImmutableAspectError):
            session.execute(
                update(EntityAspect)
                .values(payload={"new": True})
                .where(EntityAspect.id == aspect_id)
            )
            session.flush()


def test_instance_mutation_raises_immutable_aspect_error(
    aspect_session: tuple[sessionmaker, str],
) -> None:
    SessionLocal, aspect_id = aspect_session
    with SessionLocal() as session:
        aspect = session.get(EntityAspect, aspect_id)
        assert aspect is not None
        with pytest.raises(ImmutableAspectError):
            aspect.payload = {"new": True}
            session.flush()

