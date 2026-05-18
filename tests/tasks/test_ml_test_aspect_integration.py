"""Aspect integration tests for the ML test task path."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata import write_aspect
from aqp.metadata.aspect_lookup import load_aspect, load_ml_model
from aqp.metadata.openmetadata import MlHyperParameter, MlModel
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
from aqp.tasks import ml_test_tasks


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite aspect store and patch session providers."""
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

    import aqp.metadata.aspect_lookup as aspect_lookup

    monkeypatch.setattr(aspect_lookup, "get_session", _patched_get_session)
    monkeypatch.setattr(ml_test_tasks, "get_session", _patched_get_session)
    return SessionLocal


@pytest.fixture
def seeded_model(aspect_db: sessionmaker) -> dict[str, Any]:
    """Seed one ``mlModelMetadata`` aspect for test URN lookups."""
    urn = "urn:aqp:mlmodel:prod:cp2_ridge_model"
    model = MlModel(
        urn=urn,
        name="CP2 Ridge Model",
        algorithm="ridge",
        ml_hyper_parameters=[
            MlHyperParameter(
                name="alpha",
                value="0.1",
                value_type="float",
                description="L2 regularisation strength",
            )
        ],
        target="forward_return_1d",
        status="Production",
        model_version="v1",
    )
    with aspect_db() as session:
        row = write_aspect(session, urn, "mlModelMetadata", model)
        session.commit()
        assert row.version == 1
    return {"urn": urn, "payload": model.model_dump(mode="json")}


def _silence_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable websocket progress publishing for direct task invocation."""
    monkeypatch.setattr(ml_test_tasks, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ml_test_tasks, "emit_done", lambda *args, **kwargs: None)
    monkeypatch.setattr(ml_test_tasks, "emit_error", lambda *args, **kwargs: None)


def test_load_ml_model_returns_populated_instance(seeded_model: dict[str, Any]) -> None:
    """`load_ml_model` reconstructs a typed `MlModel` from aspect payload."""
    model = load_ml_model(seeded_model["urn"])
    assert model is not None
    assert model.urn == seeded_model["urn"]
    assert model.algorithm == "ridge"
    assert model.target == "forward_return_1d"


def test_load_aspect_returns_exact_v1_payload(seeded_model: dict[str, Any]) -> None:
    """Version-pinned lookup returns the exact stored payload."""
    payload = load_aspect(seeded_model["urn"], "mlModelMetadata", version=1)
    assert payload == seeded_model["payload"]


def test_ml_test_task_writes_ml_test_result_v1(
    monkeypatch: pytest.MonkeyPatch,
    aspect_db: sessionmaker,
    seeded_model: dict[str, Any],
) -> None:
    """One test run writes the first `mlTestResult` aspect version."""
    _silence_progress(monkeypatch)
    result = ml_test_tasks.run_ml_test.run(
        config={
            "algorithm": "legacy_inline_algo",
            "target": "legacy_target",
            "hyperparameters": {"alpha": 999},
            "predictions": [0.02, -0.01, 0.03, -0.02],
            "labels": [0.01, -0.02, 0.02, -0.03],
            "returns": [0.02, -0.01, 0.015, -0.005],
        },
        model_urn=seeded_model["urn"],
    )

    assert result["model_urn"] == seeded_model["urn"]
    assert result["algorithm"] == "ridge"
    assert result["target"] == "forward_return_1d"

    with aspect_db() as session:
        rows = (
            session.execute(
                select(EntityAspect)
                .where(EntityAspect.urn == seeded_model["urn"])
                .where(EntityAspect.aspect_name == "mlTestResult")
                .order_by(EntityAspect.version.asc())
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].version == 1
    assert rows[0].payload.get("model_urn") == seeded_model["urn"]


def test_second_ml_test_run_bumps_ml_test_result_version(
    monkeypatch: pytest.MonkeyPatch,
    aspect_db: sessionmaker,
    seeded_model: dict[str, Any],
) -> None:
    """Second run writes a new immutable `mlTestResult` version."""
    _silence_progress(monkeypatch)
    ml_test_tasks.run_ml_test.run(
        config={
            "predictions": [0.01, 0.02, -0.01],
            "labels": [0.0, 0.01, -0.02],
            "returns": [0.01, 0.02, -0.01],
        },
        model_urn=seeded_model["urn"],
    )
    ml_test_tasks.run_ml_test.run(
        config={
            "predictions": [0.03, -0.01, 0.02],
            "labels": [0.01, -0.02, 0.01],
            "returns": [0.03, -0.015, 0.01],
        },
        model_urn=seeded_model["urn"],
    )

    with aspect_db() as session:
        versions = (
            session.execute(
                select(EntityAspect.version)
                .where(EntityAspect.urn == seeded_model["urn"])
                .where(EntityAspect.aspect_name == "mlTestResult")
                .order_by(EntityAspect.version.asc())
            )
            .scalars()
            .all()
        )
    assert versions == [1, 2]
