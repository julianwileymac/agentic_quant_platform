"""Tests for paper-session metadata gating."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata import MetadataValidationError
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
from aqp.trading import metadata_gate
from aqp.trading.metadata_gate import assert_metadata_gate, run_metadata_gate


def _payload_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seed_model_aspect(
    SessionLocal: sessionmaker,
    *,
    urn: str,
    status: str,
) -> None:
    payload = {
        "urn": urn,
        "name": "Seeded Model",
        "algorithm": "ridge",
        "ml_features": [],
        "ml_hyper_parameters": [],
        "target": "forward_return_1d",
        "status": status,
    }
    with SessionLocal() as session:
        session.add(MetadataEntity(urn=urn, entity_type="mlmodel"))
        session.add(
            EntityAspect(
                urn=urn,
                aspect_name="mlModelMetadata",
                version=1,
                payload=payload,
                payload_hash=_payload_hash(payload),
                system_metadata={},
            )
        )
        session.commit()


def _seed_pipeline_aspect(
    SessionLocal: sessionmaker,
    *,
    urn: str,
) -> None:
    payload = {
        "urn": urn,
        "name": "Seeded Pipeline",
        "pipeline_location": "configs/paper/test.yaml",
        "tasks": [
            {
                "name": "paper_session_run",
                "task_type": "mcp_tool",
                "upstream_tasks": [],
                "description": None,
                "start_date": None,
                "end_date": None,
            }
        ],
        "start_date": None,
        "end_date": None,
    }
    with SessionLocal() as session:
        session.add(MetadataEntity(urn=urn, entity_type="pipeline"))
        session.add(
            EntityAspect(
                urn=urn,
                aspect_name="pipelineMetadata",
                version=1,
                payload=payload,
                payload_hash=_payload_hash(payload),
                system_metadata={},
            )
        )
        session.commit()


@pytest.fixture
def metadata_store(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Hermetic sqlite metadata store for gate lookups."""
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

    monkeypatch.setattr(metadata_gate, "get_session", _patched_get_session)
    monkeypatch.setattr(metadata_gate, "_load_ml_model", None)
    monkeypatch.setattr(metadata_gate, "_load_pipeline", None)
    return SessionLocal


def test_run_metadata_gate_raises_on_missing_urns() -> None:
    """Strict gate must block startup when either URN is omitted."""
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(model_urn=None, pipeline_urn=None)


def test_run_metadata_gate_raises_on_invalid_urn() -> None:
    """Malformed URNs should fail strict validation immediately."""
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(model_urn="not-a-valid-urn", pipeline_urn=None)


def test_run_metadata_gate_raises_on_missing_model_aspect(
    metadata_store: sessionmaker,
) -> None:
    """Parsed model URN with no aspect row should fail strict validation."""
    pipeline_urn = "urn:aqp:pipeline:prod:seeded_pipeline_v1"
    _seed_pipeline_aspect(metadata_store, urn=pipeline_urn)
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(
            model_urn="urn:aqp:mlmodel:prod:missing_model_v1",
            pipeline_urn=pipeline_urn,
        )


def test_run_metadata_gate_rejects_development_model(
    metadata_store: sessionmaker,
) -> None:
    """Development model status should fail the strict lifecycle gate."""
    urn = "urn:aqp:mlmodel:prod:dev_model_v1"
    pipeline_urn = "urn:aqp:pipeline:prod:dev_model_pipeline_v1"
    _seed_model_aspect(metadata_store, urn=urn, status="Development")
    _seed_pipeline_aspect(metadata_store, urn=pipeline_urn)
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(model_urn=urn, pipeline_urn=pipeline_urn)


def test_run_metadata_gate_passes_with_seeded_production_urns(
    metadata_store: sessionmaker,
) -> None:
    """Strict gate should pass for production model + resolvable pipeline."""
    model_urn = "urn:aqp:mlmodel:prod:strict_prod_model_v1"
    pipeline_urn = "urn:aqp:pipeline:prod:strict_prod_pipeline_v1"
    _seed_model_aspect(metadata_store, urn=model_urn, status="Production")
    _seed_pipeline_aspect(metadata_store, urn=pipeline_urn)
    outcome = run_metadata_gate(model_urn=model_urn, pipeline_urn=pipeline_urn)
    assert outcome.ok is True
    assert outcome.errors == ()
    assert outcome.enforced is True


def test_assert_metadata_gate_raises_on_missing_urns() -> None:
    """assert_metadata_gate should enforce strict missing-URN failures."""
    with pytest.raises(MetadataValidationError):
        assert_metadata_gate(model_urn=None, pipeline_urn=None)


def test_assert_metadata_gate_passes_with_seeded_production_urns(
    metadata_store: sessionmaker,
) -> None:
    """assert_metadata_gate should return ok=True for seeded production URNs."""
    model_urn = "urn:aqp:mlmodel:prod:assert_prod_model_v1"
    pipeline_urn = "urn:aqp:pipeline:prod:assert_prod_pipeline_v1"
    _seed_model_aspect(metadata_store, urn=model_urn, status="Production")
    _seed_pipeline_aspect(metadata_store, urn=pipeline_urn)
    outcome = assert_metadata_gate(model_urn=model_urn, pipeline_urn=pipeline_urn)
    assert outcome.ok is True
    assert outcome.errors == ()
