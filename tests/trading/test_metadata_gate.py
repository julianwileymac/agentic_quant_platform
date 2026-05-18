"""Tests for paper-session metadata gating."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.config import settings
from aqp.metadata import MetadataValidationError
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
from aqp.trading.baseline_aspects import (
    BASELINE_PAPER_CONFIGS,
    seed_paper_baseline_aspects,
)
from aqp.trading import metadata_gate
from aqp.trading.metadata_gate import run_metadata_gate


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


def test_warn_mode_without_urns_returns_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """No URNs should warn but still pass in WARN mode."""
    monkeypatch.setattr(settings, "paper_strict_metadata", False)
    outcome = run_metadata_gate(model_urn=None, pipeline_urn=None)
    assert outcome.ok is True
    assert outcome.errors == ()
    assert outcome.warnings


def test_warn_mode_invalid_urn_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid URN should fail validation without raising in WARN mode."""
    monkeypatch.setattr(settings, "paper_strict_metadata", False)
    outcome = run_metadata_gate(model_urn="not-a-valid-urn", pipeline_urn=None)
    assert outcome.ok is False
    assert outcome.errors
    assert outcome.warnings
    assert outcome.enforced is False


def test_warn_mode_missing_model_aspect(
    metadata_store: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parsed model URN with no aspect row should report a missing-aspect error."""
    _ = metadata_store
    monkeypatch.setattr(settings, "paper_strict_metadata", False)
    outcome = run_metadata_gate(
        model_urn="urn:aqp:mlmodel:prod:missing_model_v1",
        pipeline_urn=None,
    )
    assert outcome.ok is False
    assert any("not found in entity_aspects" in err for err in outcome.errors)


def test_warn_mode_rejects_development_model(
    metadata_store: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development model status should fail the lifecycle gate."""
    urn = "urn:aqp:mlmodel:prod:dev_model_v1"
    _seed_model_aspect(metadata_store, urn=urn, status="Development")
    monkeypatch.setattr(settings, "paper_strict_metadata", False)
    outcome = run_metadata_gate(model_urn=urn, pipeline_urn=None)
    assert outcome.ok is False
    assert any("is not Production/Staging" in err for err in outcome.errors)


def test_warn_mode_accepts_production_model(
    metadata_store: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production model status should pass in WARN mode."""
    urn = "urn:aqp:mlmodel:prod:prod_model_v1"
    _seed_model_aspect(metadata_store, urn=urn, status="Production")
    monkeypatch.setattr(settings, "paper_strict_metadata", False)
    outcome = run_metadata_gate(model_urn=urn, pipeline_urn=None)
    assert outcome.ok is True
    assert outcome.errors == ()


def test_strict_mode_invalid_urn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """STRICT mode should raise MetadataValidationError on invalid URNs."""
    monkeypatch.setattr(settings, "paper_strict_metadata", True)
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(model_urn="bad-urn", pipeline_urn=None)


def test_strict_default_aborts_on_missing_urn() -> None:
    """Strict default rejects startup when required URNs are omitted."""
    assert settings.paper_strict_metadata is True
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(model_urn=None, pipeline_urn=None)


def test_strict_default_aborts_on_unresolvable_urn(
    metadata_store: sessionmaker,
) -> None:
    """Strict default rejects model URNs that do not resolve to an aspect."""
    baseline_cfg = BASELINE_PAPER_CONFIGS[0]
    with metadata_store() as session:
        seed_paper_baseline_aspects(session)
        session.commit()
    assert settings.paper_strict_metadata is True
    with pytest.raises(MetadataValidationError):
        run_metadata_gate(
            model_urn="urn:aqp:mlmodel:prod:missing_model_v2",
            pipeline_urn=baseline_cfg.pipeline_urn,
        )


def test_strict_default_passes_with_seeded_baseline(
    metadata_store: sessionmaker,
) -> None:
    """Strict default accepts the built-in seeded baseline URNs."""
    baseline_cfg = BASELINE_PAPER_CONFIGS[0]
    with metadata_store() as session:
        seed_paper_baseline_aspects(session)
        session.commit()
    assert settings.paper_strict_metadata is True
    outcome = run_metadata_gate(
        model_urn=baseline_cfg.model_urn,
        pipeline_urn=baseline_cfg.pipeline_urn,
    )
    assert outcome.ok is True
    assert outcome.errors == ()


def test_strict_mode_valid_production_model_passes(
    metadata_store: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STRICT mode should permit valid model and pipeline metadata."""
    urn = "urn:aqp:mlmodel:prod:strict_prod_model_v1"
    pipeline_urn = "urn:aqp:pipeline:prod:strict_prod_pipeline_v1"
    _seed_model_aspect(metadata_store, urn=urn, status="Production")
    _seed_pipeline_aspect(metadata_store, urn=pipeline_urn)
    monkeypatch.setattr(settings, "paper_strict_metadata", True)
    outcome = run_metadata_gate(model_urn=urn, pipeline_urn=pipeline_urn)
    assert outcome.ok is True
    assert outcome.errors == ()
