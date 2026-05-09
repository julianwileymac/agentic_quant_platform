"""RL experiment spec registry — discover, load, persist :class:`RLExperimentSpec`.

Mirrors :mod:`aqp.bots.registry`:

- ``configs/rl/specs/*.yaml`` is scanned on first lookup.
- :func:`persist_spec` snapshots a spec to ``rl_experiment_versions``
  (idempotent by hash).
- :func:`replay_spec_version` rehydrates a frozen spec from the DB.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from aqp.rl.spec import RLExperimentSpec, load_specs_from_dir

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, RLExperimentSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "rl" / "specs"


def register_rl_spec(name: str | None = None):
    """Decorator: register a :class:`RLExperimentSpec` constructor / instance."""

    def decorator(target):
        spec = target() if callable(target) and not isinstance(target, RLExperimentSpec) else target
        if not isinstance(spec, RLExperimentSpec):
            raise TypeError(
                f"register_rl_spec expects RLExperimentSpec, got {type(spec).__name__}"
            )
        with _LOCK:
            if name:
                _REGISTRY[name] = spec
            _index_spec(spec)
        return target

    return decorator


def add_spec(spec: RLExperimentSpec) -> None:
    """Register an in-memory spec without going through a decorator."""
    with _LOCK:
        _index_spec(spec)


def _index_spec(spec: RLExperimentSpec) -> None:
    if spec.slug:
        _REGISTRY[spec.slug] = spec
    if spec.name and spec.name != spec.slug:
        _REGISTRY[spec.name] = spec


def list_rl_specs() -> list[RLExperimentSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        seen: set[int] = set()
        out: list[RLExperimentSpec] = []
        for spec in _REGISTRY.values():
            if id(spec) in seen:
                continue
            seen.add(id(spec))
            out.append(spec)
        return out


def get_rl_spec(name_or_slug: str) -> RLExperimentSpec:
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    _ensure_yaml_scan()
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    raise KeyError(f"No RL experiment spec registered under {name_or_slug!r}")


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
            if spec.slug and spec.slug not in _REGISTRY:
                _REGISTRY[spec.slug] = spec
            if spec.name and spec.name not in _REGISTRY:
                _REGISTRY[spec.name] = spec


def reload_yaml_dir(path: str | Path | None = None) -> int:
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_specs_from_dir(str(target)):
        with _LOCK:
            _index_spec(spec)
        n += 1
    return n


def persist_spec(spec: RLExperimentSpec, *, project_id: str | None = None) -> str | None:
    """Snapshot ``spec`` into ``rl_experiment_versions`` (idempotent by hash).

    Returns the version row id, or ``None`` if Postgres is unavailable —
    matches the bot/agent ``persist_spec`` behaviour so the runtime can
    keep going with no persistence layer.
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import RLExperimentSpec as RLSpecRow
        from aqp.persistence.models_rl import RLExperimentVersion
    except Exception:  # pragma: no cover
        logger.debug("RL persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = (
                session.query(RLSpecRow)
                .filter(RLSpecRow.slug == spec.slug)
                .one_or_none()
            )
            if row is None:
                row = RLSpecRow(
                    name=spec.name,
                    slug=spec.slug,
                    kind=spec.kind,
                    description=spec.description,
                    current_version=1,
                    spec_yaml=spec.to_yaml(),
                    status="draft",
                    annotations=list(spec.annotations or []),
                )
                if project_id:
                    row.project_id = project_id
                session.add(row)
                session.flush()
            existing = (
                session.query(RLExperimentVersion)
                .filter(RLExperimentVersion.spec_hash == sha)
                .filter(RLExperimentVersion.spec_id == row.id)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(RLExperimentVersion)
                .filter(RLExperimentVersion.spec_id == row.id)
                .count()
                + 1
            )
            version_row = RLExperimentVersion(
                spec_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=payload,
            )
            session.add(version_row)
            row.current_version = next_version
            row.kind = spec.kind
            row.name = spec.name
            row.description = spec.description
            row.spec_yaml = spec.to_yaml()
            row.annotations = list(spec.annotations or [])
            session.commit()
            return version_row.id
    except Exception:  # noqa: BLE001
        logger.exception("persist_spec failed for RL experiment %s", spec.name)
        return None


def replay_spec_version(version_id: str) -> RLExperimentSpec:
    """Load a frozen RL spec back from ``rl_experiment_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_rl import RLExperimentVersion

    with SessionLocal() as session:
        row = (
            session.query(RLExperimentVersion)
            .filter(RLExperimentVersion.id == version_id)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"No RL experiment version {version_id!r}")
        return RLExperimentSpec.model_validate(row.payload)


__all__ = [
    "add_spec",
    "get_rl_spec",
    "list_rl_specs",
    "persist_spec",
    "register_rl_spec",
    "reload_yaml_dir",
    "replay_spec_version",
]
