"""Tests for pulling DataHub aspects into AQP entity_aspects."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.datahub import aspect_puller
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


class _MockClient:
    def get_aspect(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = (args, kwargs)
        return {
            "name": "lstm_v1",
            "description": "Model metadata from DataHub",
            "customProperties": {"framework": "pytorch"},
        }

    def get_latest_aspects(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = (args, kwargs)
        return {}


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create an isolated sqlite store for aspect pull tests."""
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

    monkeypatch.setattr(aspect_puller, "get_session", _patched_get_session)
    return SessionLocal


def test_pull_aspect_writes_entity_aspect_row(
    aspect_db: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pull_aspect persists a DataHub class payload via write_aspect."""
    mock_client = _MockClient()
    monkeypatch.setattr(aspect_puller, "_resolve_aspect_client", lambda: (mock_client, None))
    monkeypatch.setattr(
        aspect_puller,
        "_load_schema_class",
        lambda class_name: class_name,
    )

    result = aspect_puller.pull_aspect(
        datahub_urn="urn:li:mlModel:(urn:li:dataPlatform:aqp,lstm_v1,PROD)",
        aspect_class_name="MLModelPropertiesClass",
    )
    assert result["pulled"] is True

    with aspect_db() as session:
        row = session.execute(select(EntityAspect).limit(1)).scalar_one()
    assert row.aspect_name == "mlModelMetadata"
    assert row.system_metadata["source"] == "datahub"
    assert row.system_metadata["datahub_urn"] == "urn:li:mlModel:(urn:li:dataPlatform:aqp,lstm_v1,PROD)"
