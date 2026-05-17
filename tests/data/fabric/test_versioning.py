from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from aqp.data.fabric.identity import FabricIdentity, VersionVector
from aqp.data.fabric.versioning import (
    VersionConflictError,
    VersionManager,
    verify_lineage_chain,
)
from aqp.persistence.models import Base
from aqp.persistence.models_ingestion_ledger import FabricVersionSnapshot
from aqp.persistence.models_lineage import DataLineageEvent


@pytest.fixture
def session() -> Iterator[Session]:
    from aqp.persistence import (  # noqa: F401 - register tables onto Base.metadata
        models_ingestion_ledger,
        models_lineage,
        models_tenancy,
    )

    engine = create_engine("sqlite:///:memory:", future=True)
    tables = [
        Base.metadata.tables["organizations"],
        Base.metadata.tables["users"],
        Base.metadata.tables["workspaces"],
        Base.metadata.tables["projects"],
        Base.metadata.tables["data_lineage_events"],
        Base.metadata.tables["fabric_version_snapshots"],
    ]
    Base.metadata.create_all(engine, tables=tables)

    session_local = sessionmaker(bind=engine, future=True)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


class _ToyFabric(FabricIdentity):
    """Minimal FabricIdentity concrete type used in tests."""

    def __init__(self, name: str, value: int = 0) -> None:
        self.name = name
        self.value = value
        self._seal()


def test_version_manager_increment_bumps_clock_and_hash() -> None:
    obj = _ToyFabric("alpha", 1)
    initial_hash = obj.content_hash
    initial_vec = obj.version_vector
    mgr = VersionManager()

    new_vec = mgr.increment(obj)

    assert new_vec.get(type(obj).__qualname__) == initial_vec.get(type(obj).__qualname__) + 1
    assert obj.content_hash != initial_hash


def test_check_compatibility_dominates() -> None:
    v1 = VersionVector({"X": 3, "Y": 1})
    v2 = VersionVector({"X": 2, "Y": 1})
    v3 = VersionVector({"X": 4, "Y": 1})

    assert VersionManager.check_compatibility(v1, v2) is True
    assert VersionManager.check_compatibility(v1, v3) is False


def test_resolve_conflict_returns_merge() -> None:
    v1 = VersionVector({"X": 3, "Y": 1})
    v2 = VersionVector({"X": 2, "Y": 5, "Z": 1})

    merged = VersionManager.resolve_conflict(v1, v2)

    assert merged.to_dict() == {"X": 3, "Y": 5, "Z": 1}


def test_persist_snapshot_writes_row(session: Session) -> None:
    mgr = VersionManager()
    obj = _ToyFabric("beta", 7)

    snap_id = mgr.persist_snapshot(obj, object_kind="toy", session=session)
    session.commit()

    row = session.query(FabricVersionSnapshot).filter_by(id=snap_id).one()
    assert row.object_kind == "toy"
    assert row.fabric_uuid == str(obj.fabric_uuid)
    assert row.content_hash == obj.compute_hash()


def test_verify_lineage_chain_clean(session: Session) -> None:
    obj = _ToyFabric("gamma", 1)
    mgr = VersionManager()

    mgr.persist_snapshot(obj, object_kind="toy", session=session)
    mgr.increment(obj)
    mgr.persist_snapshot(obj, object_kind="toy", session=session)

    session.add(
        DataLineageEvent(
            run_id=str(obj.fabric_uuid),
            transform_kind="materialize",
            owner_user_id=None,
            workspace_id=None,
            project_id=None,
        )
    )
    session.commit()

    result = verify_lineage_chain(uuid.UUID(str(obj.fabric_uuid)), session=session)
    assert result["ok"] is True
    assert result["checked"] == 2
    assert result["mismatches"] == []
    assert result["lineage_events"] == 1


def test_verify_lineage_chain_detects_tamper(session: Session) -> None:
    obj = _ToyFabric("delta", 99)
    mgr = VersionManager()

    snap_id = mgr.persist_snapshot(obj, object_kind="toy", session=session)
    session.commit()

    row = session.query(FabricVersionSnapshot).filter_by(id=snap_id).one()
    snapshot_data = dict(row.snapshot_data or {})
    snapshot_data["value"] = 12345
    row.snapshot_data = snapshot_data
    session.commit()

    result = verify_lineage_chain(obj.fabric_uuid, session=session)
    assert result["ok"] is False
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["snapshot_id"] == snap_id


def test_version_conflict_error_is_runtime_error() -> None:
    err = VersionConflictError("conflict")
    assert isinstance(err, RuntimeError)
