"""Workflow spec registry + immutable hash-locked persistence.

Mirrors :mod:`aqp.agents.registry` (the AgentSpec registry) one-for-one
so workflow specs share the same code-driven + YAML-driven loading
semantics, the same in-memory ``_REGISTRY`` discipline, and the same
``persist_spec`` / ``replay_spec_version`` ergonomics.

Two access modes:

- **Code-driven**: ``register_workflow("name")(spec_instance)``
  pre-loads built-in specs at import time so they're available in
  every process without DB access.
- **YAML-driven**: ``configs/workflows/*.yaml`` is scanned on first
  lookup for any spec not already registered. Discovered specs are
  added to the in-memory registry and snapshotted to
  ``workflow_spec_versions`` the first time they're persisted via
  :func:`persist_spec`.

Persistence gating
------------------
:func:`persist_spec` returns ``None`` when
``settings.orchestration_workflow_versioning_enabled`` is ``False`` so
operators can run the entire workflow pipeline in-memory while the
ORM tables roll out. Flipping the flag activates the write-through.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from pathlib import Path

from aqp.agents.orchestration.spec import (
    WorkflowSpec,
    load_workflow_specs_from_dir,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, WorkflowSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "workflows"


def register_workflow(name: str | None = None):
    """Decorator: register a :class:`WorkflowSpec` constructor / instance."""

    def decorator(target):
        spec = (
            target()
            if callable(target) and not isinstance(target, WorkflowSpec)
            else target
        )
        if not isinstance(spec, WorkflowSpec):
            raise TypeError(
                f"register_workflow expects WorkflowSpec, got {type(spec).__name__}"
            )
        slug = name or spec.name
        with _LOCK:
            _REGISTRY[slug] = spec
        return target

    return decorator


def add_workflow_spec(spec: WorkflowSpec) -> None:
    """Register an in-memory spec without going through the decorator."""
    with _LOCK:
        _REGISTRY[spec.name] = spec


def list_workflow_specs() -> list[WorkflowSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        return list(_REGISTRY.values())


def get_workflow_spec(name: str) -> WorkflowSpec:
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    _ensure_yaml_scan()
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    raise KeyError(f"No workflow spec registered under {name!r}")


def reload_yaml_dir(path: str | Path | None = None) -> int:
    """Re-read all YAML workflow specs under ``path`` (or the default dir)."""
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_workflow_specs_from_dir(str(target)):
        with _LOCK:
            _REGISTRY[spec.name] = spec
        n += 1
    return n


def clear_workflow_registry() -> None:
    """Test-only helper. Clears the in-memory registry between tests."""
    with _LOCK:
        _REGISTRY.clear()
        _DIR_SCANNED.clear()


def _ensure_yaml_scan() -> None:
    key = str(_DEFAULT_DIR.resolve())
    with _LOCK:
        if key in _DIR_SCANNED:
            return
        _DIR_SCANNED.add(key)
    if not _DEFAULT_DIR.exists():
        return
    for spec in load_workflow_specs_from_dir(str(_DEFAULT_DIR)):
        with _LOCK:
            _REGISTRY.setdefault(spec.name, spec)


def persist_spec(spec: WorkflowSpec) -> str | None:
    """Snapshot ``spec`` into ``workflow_spec_versions`` (idempotent by hash).

    Returns the spec_version_id for downstream FK use, or ``None`` if:

    - ``settings.orchestration_workflow_versioning_enabled`` is False, or
    - the Phase 5 ORM module can't be imported, or
    - Postgres is unavailable.

    Hash-locked + immutable: re-snapshotting a spec with the same
    hash returns the existing version id; a changed hash inserts a
    NEW row (parallel to ``aqp.agents.registry.persist_spec``).
    """
    if not getattr(settings, "orchestration_workflow_versioning_enabled", False):
        logger.debug(
            "workflow versioning disabled; skipping persist_spec for %s",
            spec.name,
        )
        return None
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_workflows import (
            WorkflowSpecRow,
            WorkflowSpecVersion,
        )
    except Exception:  # pragma: no cover
        logger.debug("workflow persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = (
                session.query(WorkflowSpecRow)
                .filter(WorkflowSpecRow.name == spec.name)
                .one_or_none()
            )
            if row is None:
                row = WorkflowSpecRow(
                    name=spec.name,
                    adapter=spec.adapter,
                    description=spec.description,
                    current_version=1,
                    annotations=spec.annotations,
                )
                session.add(row)
                session.flush()
            existing = (
                session.query(WorkflowSpecVersion)
                .filter(WorkflowSpecVersion.spec_hash == sha)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(WorkflowSpecVersion)
                .filter(WorkflowSpecVersion.spec_id == row.id)
                .count()
                + 1
            )
            version_row = WorkflowSpecVersion(
                spec_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=payload,
            )
            session.add(version_row)
            row.current_version = next_version
            row.adapter = spec.adapter
            row.description = spec.description
            row.annotations = spec.annotations
            session.commit()
            return version_row.id
    except Exception:  # noqa: BLE001
        logger.exception("persist_spec failed for %s", spec.name)
        return None


def replay_workflow_spec_version(version_id: str) -> WorkflowSpec:
    """Load a frozen workflow spec back from ``workflow_spec_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_workflows import WorkflowSpecVersion

    with SessionLocal() as session:
        row = (
            session.query(WorkflowSpecVersion)
            .filter(WorkflowSpecVersion.id == version_id)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"No workflow spec version {version_id!r}")
        return WorkflowSpec.model_validate(row.payload)


__all__ = [
    "add_workflow_spec",
    "clear_workflow_registry",
    "get_workflow_spec",
    "list_workflow_specs",
    "persist_spec",
    "register_workflow",
    "reload_yaml_dir",
    "replay_workflow_spec_version",
]
