"""Agent registry: discover, load, and persist :class:`AgentSpec` instances.

Two access modes:

- **Code-driven**: ``@register_agent("research.equity")(AgentSpec(...))``
  pre-loads built-in specs at import time so they're available in
  every process without DB access.
- **YAML-driven**: ``configs/agents/*.yaml`` is scanned on first lookup
  for any spec not already registered. Discovered specs are added to
  the in-memory registry **and** snapshotted to ``agent_spec_versions``
  the first time they're persisted via :func:`persist_spec`.

Looking up by name (``get_agent_spec("name")``) returns the in-memory
spec; if the spec doesn't exist the registry triggers a YAML rescan
before raising.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from pathlib import Path

from aqp.agents.spec import AgentSpec, load_specs_from_dir

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, AgentSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "agents"


def register_agent(name: str | None = None):
    """Decorator: register an :class:`AgentSpec` constructor / instance."""

    def decorator(target):
        spec = target() if callable(target) and not isinstance(target, AgentSpec) else target
        if not isinstance(spec, AgentSpec):
            raise TypeError(f"register_agent expects AgentSpec, got {type(spec).__name__}")
        slug = name or spec.name
        with _LOCK:
            _REGISTRY[slug] = spec
        return target

    return decorator


def add_spec(spec: AgentSpec) -> None:
    """Register an in-memory spec without going through a decorator."""
    with _LOCK:
        _REGISTRY[spec.name] = spec


def list_agent_specs() -> list[AgentSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        return list(_REGISTRY.values())


def get_agent_spec(name: str) -> AgentSpec:
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    _ensure_yaml_scan()
    with _LOCK:
        if name in _REGISTRY:
            return _REGISTRY[name]
    raise KeyError(f"No agent spec registered under {name!r}")


def _ensure_yaml_scan() -> None:
    key = str(_DEFAULT_DIR.resolve())
    with _LOCK:
        if key in _DIR_SCANNED:
            return
        _DIR_SCANNED.add(key)
    if not _DEFAULT_DIR.exists():
        return
    for spec in load_specs_from_dir(str(_DEFAULT_DIR)):
        with _LOCK:
            _REGISTRY.setdefault(spec.name, spec)


def reload_yaml_dir(path: str | Path | None = None) -> int:
    """Re-read all YAML specs under ``path`` (or the default dir)."""
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_specs_from_dir(str(target)):
        with _LOCK:
            _REGISTRY[spec.name] = spec
        n += 1
    return n


def persist_spec(spec: AgentSpec) -> str | None:
    """Snapshot ``spec`` into ``agent_spec_versions`` (idempotent by hash).

    Returns the spec_version_id for downstream FK use, or ``None`` if
    Postgres is unavailable.
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_agents import AgentSpecRow, AgentSpecVersion
    except Exception:  # pragma: no cover
        logger.debug("AgentSpec persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = session.query(AgentSpecRow).filter(AgentSpecRow.name == spec.name).one_or_none()
            if row is None:
                row = AgentSpecRow(
                    name=spec.name,
                    role=spec.role,
                    description=spec.description,
                    current_version=1,
                    tags=spec.annotations,
                )
                session.add(row)
                session.flush()
            existing = (
                session.query(AgentSpecVersion)
                .filter(AgentSpecVersion.spec_hash == sha)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(AgentSpecVersion)
                .filter(AgentSpecVersion.spec_id == row.id)
                .count()
                + 1
            )
            version_row = AgentSpecVersion(
                spec_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=payload,
            )
            session.add(version_row)
            row.current_version = next_version
            row.role = spec.role
            row.description = spec.description
            row.tags = spec.annotations
            session.commit()
            return version_row.id
    except Exception:  # noqa: BLE001
        logger.exception("persist_spec failed for %s", spec.name)
        return None


def replay_spec_version(version_id: str) -> AgentSpec:
    """Load a frozen spec back from ``agent_spec_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_agents import AgentSpecVersion

    with SessionLocal() as session:
        row = session.query(AgentSpecVersion).filter(AgentSpecVersion.id == version_id).one_or_none()
        if row is None:
            raise KeyError(f"No agent spec version {version_id!r}")
        return AgentSpec.model_validate(row.payload)


__all__ = [
    "add_spec",
    "get_agent_spec",
    "list_agent_specs",
    "persist_spec",
    "register_agent",
    "reload_yaml_dir",
    "replay_spec_version",
]
