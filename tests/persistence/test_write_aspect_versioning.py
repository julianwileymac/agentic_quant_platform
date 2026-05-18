"""Versioning + dedupe tests for ``write_aspect``."""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata import make_urn, write_aspect
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


class DemoPayload(BaseModel):
    field: str
    count: int


def test_write_aspect_idempotency_and_version_bumps() -> None:
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
    urn_primary = make_urn("dataset", "dev", "foo.bar")
    urn_secondary = make_urn("dataset", "dev", "bar.baz")

    with SessionLocal() as session:
        payload_v1 = DemoPayload(field="alpha", count=1)
        row_1 = write_aspect(session, urn_primary, "datasetProperties", payload_v1)
        row_1_b = write_aspect(session, urn_primary, "datasetProperties", payload_v1)
        row_1_c = write_aspect(session, urn_primary, "datasetProperties", payload_v1)
        assert row_1.id == row_1_b.id == row_1_c.id
        assert row_1.version == 1

        payload_v2 = DemoPayload(field="alpha", count=2)
        row_2 = write_aspect(session, urn_primary, "datasetProperties", payload_v2)
        assert row_2.version == 2
        assert row_2.id != row_1.id

        payload_v3 = DemoPayload(field="beta", count=3)
        row_3 = write_aspect(session, urn_primary, "datasetProperties", payload_v3)
        assert row_3.version == 3
        assert row_3.id not in {row_1.id, row_2.id}

        row_secondary = write_aspect(
            session,
            urn_secondary,
            "datasetProperties",
            DemoPayload(field="alpha", count=1),
        )
        assert row_secondary.version == 1

        session.commit()

    with SessionLocal() as session:
        primary_versions = (
            session.execute(
                select(EntityAspect.version)
                .where(
                    EntityAspect.urn == urn_primary,
                    EntityAspect.aspect_name == "datasetProperties",
                )
                .order_by(EntityAspect.version.asc())
            )
            .scalars()
            .all()
        )
        secondary_versions = (
            session.execute(
                select(EntityAspect.version).where(
                    EntityAspect.urn == urn_secondary,
                    EntityAspect.aspect_name == "datasetProperties",
                )
            )
            .scalars()
            .all()
        )
        assert primary_versions == [1, 2, 3]
        assert secondary_versions == [1]

