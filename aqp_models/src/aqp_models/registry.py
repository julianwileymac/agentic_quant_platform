"""MLSkill registry — discover, load, and persist :class:`MLSkillSpec`.

Mirrors :func:`aqp.agents.registry.persist_spec` /
:func:`aqp.bots.registry.persist_spec`. Two access modes:

- **Code-driven**: ``register_skill(MLSkillSpec(...))`` pre-loads
  built-in specs at import time so they are available without DB
  access (useful for tests).
- **YAML-driven**: ``aqp_models/configs/skills/*.yaml`` is scanned on
  first lookup. Discovered specs are added to the in-memory registry
  AND snapshotted to ``ml_skill_versions`` the first time they are
  persisted via :func:`persist_spec`.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from aqp_models.spec import MLSkillSpec, load_skill_specs_from_dir

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, MLSkillSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "skills"


def add_spec(spec: MLSkillSpec) -> None:
    """Register a skill in-memory without going through a decorator."""
    with _LOCK:
        _REGISTRY[spec.name] = spec


def register_skill(spec: MLSkillSpec) -> MLSkillSpec:
    """Decorator-style helper for code-driven seeds."""
    add_spec(spec)
    return spec


def list_skill_specs() -> list[MLSkillSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        return list(_REGISTRY.values())


def get_skill_spec(name: str) -> MLSkillSpec:
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    _ensure_yaml_scan()
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    raise KeyError(f"No MLSkillSpec registered under {name!r}")


def reload_yaml_dir(path: str | Path | None = None) -> int:
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_skill_specs_from_dir(str(target)):
        with _LOCK:
            _REGISTRY[spec.name] = spec
        n += 1
    return n


def persist_spec(spec: MLSkillSpec) -> str | None:
    """Snapshot ``spec`` into ``ml_skill_versions`` (idempotent by hash).

    Returns the new version-row id, or ``None`` when Postgres /
    ``models_mlops`` is unavailable. The first call inserts a parent
    ``ml_skills`` row keyed by ``spec.name``; subsequent calls increment
    ``current_version`` only when the spec hash actually changed.
    """
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_mlops import MlSkill, MlSkillVersion
    except Exception:  # pragma: no cover
        logger.debug("MLSkill persistence unavailable", exc_info=True)
        return None

    sha = spec.spec_hash()
    payload = spec.canonical_body()
    try:
        with get_session() as session:
            row = session.query(MlSkill).filter(MlSkill.name == spec.name).one_or_none()
            if row is None:
                row = MlSkill(
                    name=spec.name,
                    description=spec.description,
                    kind=spec.kind,
                    current_version=1,
                    annotations=list(spec.annotations),
                    workspace_id=spec.workspace_id,
                    project_id=spec.project_id,
                )
                session.add(row)
                session.flush()
            existing = (
                session.query(MlSkillVersion)
                .filter(MlSkillVersion.spec_hash == sha)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(MlSkillVersion)
                .filter(MlSkillVersion.skill_id == row.id)
                .count()
                + 1
            )
            ver = MlSkillVersion(
                skill_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=payload,
            )
            session.add(ver)
            session.flush()
            row.current_version = next_version
            row.description = spec.description
            row.annotations = list(spec.annotations)
            return ver.id
    except Exception:  # noqa: BLE001
        logger.exception("persist_spec failed for %s", spec.name)
        return None


def replay_spec_version(version_id: str) -> MLSkillSpec:
    """Re-hydrate a frozen spec from ``ml_skill_versions``."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_mlops import MlSkillVersion

    with get_session() as session:
        row = session.get(MlSkillVersion, version_id)
        if row is None:
            raise KeyError(f"No MLSkillSpec version {version_id!r}")
        return MLSkillSpec.model_validate(row.payload)


def _ensure_yaml_scan() -> None:
    key = str(_DEFAULT_DIR.resolve())
    with _LOCK:
        if key in _DIR_SCANNED:
            return
        _DIR_SCANNED.add(key)
    if not _DEFAULT_DIR.exists():
        return
    for spec in load_skill_specs_from_dir(str(_DEFAULT_DIR)):
        with _LOCK:
            _REGISTRY.setdefault(spec.name, spec)


__all__ = [
    "add_spec",
    "get_skill_spec",
    "list_skill_specs",
    "persist_spec",
    "register_skill",
    "reload_yaml_dir",
    "replay_spec_version",
]
