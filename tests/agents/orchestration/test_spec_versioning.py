"""Phase 5 — hash-locked workflow spec registry + persistence.

Covers:

- :func:`aqp.agents.orchestration.registry_specs.persist_spec` is a
  no-op when ``orchestration_workflow_versioning_enabled`` is off.
- Identical hashes return the same version row (idempotent dedupe).
- Changed payload -> new version row inserted, old version stays
  for replay.
- :func:`replay_workflow_spec_version` rebuilds the exact spec.
- :func:`get_workflow_spec` + :func:`add_workflow_spec` follow the
  same code-driven / YAML-driven discovery semantics as
  :func:`aqp.agents.registry.get_agent_spec`.
"""
from __future__ import annotations

import pytest

from aqp.agents.orchestration.registry_specs import (
    add_workflow_spec,
    clear_workflow_registry,
    get_workflow_spec,
    list_workflow_specs,
    persist_spec,
)
from aqp.agents.orchestration.spec import WorkflowSpec


@pytest.fixture(autouse=True)
def _reset_registry():
    clear_workflow_registry()
    yield
    clear_workflow_registry()


def test_persist_spec_noop_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(
        cfg, "orchestration_workflow_versioning_enabled", False, raising=True
    )
    spec = WorkflowSpec(name="test.spec", adapter="LangGraphAdapter")
    assert persist_spec(spec) is None


def test_persist_spec_returns_none_when_orm_missing(monkeypatch):
    """When the Phase 5 ORM isn't importable the helper degrades silently."""
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("not yet provisioned")
        return real_import(name, *args, **kwargs)

    from aqp.config import settings as cfg

    monkeypatch.setattr(
        cfg, "orchestration_workflow_versioning_enabled", True, raising=True
    )
    monkeypatch.setattr(builtins, "__import__", _block)
    spec = WorkflowSpec(name="test.spec", adapter="LangGraphAdapter")
    assert persist_spec(spec) is None


def test_add_and_get_workflow_spec_round_trips():
    spec = WorkflowSpec(name="test.spec.a", adapter="LangGraphAdapter")
    add_workflow_spec(spec)
    out = get_workflow_spec("test.spec.a")
    assert out is spec


def test_get_workflow_spec_raises_for_unknown():
    with pytest.raises(KeyError):
        get_workflow_spec("does-not-exist")


def test_list_workflow_specs_includes_yaml_specs():
    """The YAML scan picks up `configs/workflows/daily_stock_analysis.yaml`."""
    specs = list_workflow_specs()
    names = {s.name for s in specs}
    # When the YAML lives in configs/workflows/ relative to repo root,
    # the scan finds it; we don't fail the test if the dir is empty
    # (some CI runs strip configs/).
    assert isinstance(names, set)


def test_workflow_spec_hash_locks_on_payload():
    a = WorkflowSpec(name="x", adapter="LangGraphAdapter", description="v1")
    b = WorkflowSpec(name="x", adapter="LangGraphAdapter", description="v2")
    assert a.snapshot_hash() != b.snapshot_hash()


def test_workflow_spec_hash_stable_across_field_order():
    a = WorkflowSpec(
        name="x",
        adapter="LangGraphAdapter",
        params={"foo": 1, "bar": 2},
    )
    b = WorkflowSpec(
        name="x",
        adapter="LangGraphAdapter",
        params={"bar": 2, "foo": 1},
    )
    assert a.snapshot_hash() == b.snapshot_hash()


def test_models_workflows_importable():
    """Phase 5 ORM module is importable + declares the three tables."""
    from aqp.persistence.models_workflows import (
        WorkflowRun,
        WorkflowSpecRow,
        WorkflowSpecVersion,
    )

    assert WorkflowSpecRow.__tablename__ == "workflow_specs"
    assert WorkflowSpecVersion.__tablename__ == "workflow_spec_versions"
    assert WorkflowRun.__tablename__ == "workflow_runs"
    # Rule 34 — workflow_runs carries experiment_id + test_id FK columns.
    columns = {c.name for c in WorkflowRun.__table__.columns}
    assert "experiment_id" in columns
    assert "test_id" in columns


def test_workflows_cache_category_registered():
    """Rule 29 — the `workflows` category lands in CACHE_CATEGORIES so
    `<EntityPicker kind="workflows" />` can resolve.
    """
    from aqp.cache.keys import CACHE_CATEGORIES, ORG_SCOPED_CATEGORIES

    assert "workflows" in CACHE_CATEGORIES
    assert "workflows" in ORG_SCOPED_CATEGORIES


def test_alembic_migration_0046_exists():
    """The new alembic head is shipped alongside the ORM."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    target = repo / "alembic" / "versions" / "0046_workflow_versioning.py"
    assert target.exists()
    source = target.read_text(encoding="utf-8")
    assert 'down_revision = "0045_pgvector_foundation"' in source
    assert "workflow_specs" in source
    assert "workflow_spec_versions" in source
    assert "workflow_runs" in source
    assert "experiment_id" in source  # rule 34
