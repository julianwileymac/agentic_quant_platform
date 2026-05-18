"""Tests for DataHub EntityAspect emission helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.data.datahub import aspect_emitter
from aqp.data.datahub.aspect_mapping import aqp_urn_to_datahub_entity_urn
from aqp.metadata import write_aspect
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity


class _Payload(BaseModel):
    name: str
    description: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


class _MockMCP:
    def __init__(self, *, entityUrn: str, aspect: Any) -> None:
        self.entityUrn = entityUrn
        self.aspect = aspect


class _MockEmitter:
    def __init__(self) -> None:
        self.events: list[_MockMCP] = []

    def emit_mcp(self, event: _MockMCP) -> None:
        self.events.append(event)

    def emit(self, event: _MockMCP) -> None:
        self.events.append(event)


class _MockClient:
    def __init__(self, emitter: _MockEmitter) -> None:
        self._emitter = emitter

    def emitter(self) -> _MockEmitter:
        return self._emitter


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Provide an isolated sqlite aspect store."""
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

    monkeypatch.setattr(aspect_emitter, "get_session", _patched_get_session)
    monkeypatch.setattr(aspect_emitter, "_start_log_entry", lambda **kwargs: {})
    monkeypatch.setattr(aspect_emitter, "_finalize_log_entry", lambda *args, **kwargs: None)
    return SessionLocal


@pytest.fixture
def mock_datahub(monkeypatch: pytest.MonkeyPatch) -> _MockEmitter:
    """Patch DataHub dependencies with deterministic test doubles."""
    emitter = _MockEmitter()
    monkeypatch.setattr(aspect_emitter, "get_client", lambda: _MockClient(emitter))
    monkeypatch.setattr(aspect_emitter, "_load_mcp_wrapper", lambda: _MockMCP)
    monkeypatch.setattr(
        aspect_emitter,
        "build_datahub_aspect",
        lambda aspect_name, payload: {"aspect_name": aspect_name, "payload": payload},
    )
    return emitter


def test_push_aspect_emits_single_mcp_event(
    aspect_db: sessionmaker,
    mock_datahub: _MockEmitter,
) -> None:
    """push_aspect emits exactly one MCP when one aspect row is selected."""
    urn = "urn:aqp:mlmodel:prod:lstm_v1"
    with aspect_db() as session:
        write_aspect(
            session,
            urn,
            "mlModelMetadata",
            _Payload(name="lstm_v1", description="LSTM model"),
        )
        session.commit()

    result = aspect_emitter.push_aspect(urn=urn, aspect_name="mlModelMetadata")
    assert result["emitted"] is True
    assert result["n_aspects"] == 1
    assert len(mock_datahub.events) == 1
    assert mock_datahub.events[0].entityUrn == aqp_urn_to_datahub_entity_urn(urn)


def test_push_all_aspects_emits_every_row(
    aspect_db: sessionmaker,
    mock_datahub: _MockEmitter,
) -> None:
    """push_all_aspects emits one MCP event per selected EntityAspect row."""
    with aspect_db() as session:
        write_aspect(
            session,
            "urn:aqp:dataset:prod:prices.daily",
            "datasetProperties",
            _Payload(name="prices.daily", description="dataset"),
        )
        write_aspect(
            session,
            "urn:aqp:dataset:prod:prices.daily",
            "businessMetadata",
            _Payload(name="prices.daily", description="tags"),
        )
        write_aspect(
            session,
            "urn:aqp:mlmodel:prod:lstm_v1",
            "mlModelMetadata",
            _Payload(name="lstm_v1", description="model"),
        )
        write_aspect(
            session,
            "urn:aqp:mlmodel:prod:lstm_v1",
            "mlTestResult",
            _Payload(name="lstm_v1", description="tests"),
        )
        session.commit()

    result = aspect_emitter.push_all_aspects()
    assert result["emitted_count"] == 4
    assert result["skipped_count"] == 0
    assert len(mock_datahub.events) == 4
