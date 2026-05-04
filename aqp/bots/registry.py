"""Bot registry: discover, load, and persist :class:`BotSpec` instances.

Two access modes:

- **Code-driven**: ``@register_bot_spec("dual-ma-aapl")(BotSpec(...))``
  pre-loads built-in specs at import time so they're available in
  every process without DB access.
- **YAML-driven**: ``configs/bots/<kind>/*.yaml`` is scanned on first
  lookup for any spec not already registered. Discovered specs are
  added to the in-memory registry **and** snapshotted to ``bot_versions``
  the first time they're persisted via :func:`persist_spec`.

Looking up by name (``get_bot_spec("name")``) returns the in-memory
spec; if the spec doesn't exist the registry triggers a YAML rescan
before raising.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from aqp.bots.spec import BotSpec, load_specs_from_dir

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, BotSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "bots"


def register_bot_spec(name: str | None = None):
    """Decorator: register a :class:`BotSpec` constructor / instance.

    ``name`` overrides the lookup key; otherwise the spec's ``slug``
    (preferred) and ``name`` both index into the registry so callers can
    use either identifier interchangeably.
    """

    def decorator(target):
        spec = target() if callable(target) and not isinstance(target, BotSpec) else target
        if not isinstance(spec, BotSpec):
            raise TypeError(f"register_bot_spec expects BotSpec, got {type(spec).__name__}")
        with _LOCK:
            if name:
                _REGISTRY[name] = spec
            _index_spec(spec)
        return target

    return decorator


def add_spec(spec: BotSpec) -> None:
    """Register an in-memory spec without going through a decorator.

    Indexes the spec under both its ``slug`` and ``name`` so lookup is
    forgiving (mirrors the CLI / REST experience where users may type
    either).
    """
    with _LOCK:
        _index_spec(spec)


def _index_spec(spec: BotSpec) -> None:
    """Insert ``spec`` into the registry under every identifier we accept."""
    if spec.slug:
        _REGISTRY[spec.slug] = spec
    if spec.name and spec.name != spec.slug:
        _REGISTRY[spec.name] = spec


def list_bot_specs() -> list[BotSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        # De-duplicate — a spec is typically indexed twice (slug + name).
        seen: set[int] = set()
        out: list[BotSpec] = []
        for spec in _REGISTRY.values():
            if id(spec) in seen:
                continue
            seen.add(id(spec))
            out.append(spec)
        return out


def get_bot_spec(name_or_slug: str) -> BotSpec:
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    _ensure_yaml_scan()
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    raise KeyError(f"No bot spec registered under {name_or_slug!r}")


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
            # Only fill slots that don't already have a programmatically
            # registered spec.
            if spec.slug and spec.slug not in _REGISTRY:
                _REGISTRY[spec.slug] = spec
            if spec.name and spec.name not in _REGISTRY:
                _REGISTRY[spec.name] = spec


def reload_yaml_dir(path: str | Path | None = None) -> int:
    """Re-read all YAML specs under ``path`` (or the default dir).

    Replaces in-memory entries (unlike the lazy first-scan path which
    only fills missing slots).
    """
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_specs_from_dir(str(target)):
        with _LOCK:
            _index_spec(spec)
        n += 1
    return n


def persist_spec(spec: BotSpec, *, project_id: str | None = None) -> str | None:
    """Snapshot ``spec`` into ``bot_versions`` (idempotent by hash).

    Mirrors :func:`aqp.agents.registry.persist_spec`:

    1. Upserts the logical :class:`Bot` row by ``(project_id, slug)``.
    2. Returns the ``BotVersion.id`` if a row with the same hash already
       exists; otherwise inserts a new immutable version row and bumps
       :attr:`Bot.current_version`.

    Returns ``None`` if Postgres is unavailable so the runtime can keep
    going without persistence (matches the agents path).
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_bots import Bot as BotRow
        from aqp.persistence.models_bots import BotVersion
    except Exception:  # pragma: no cover
        logger.debug("Bot persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = (
                session.query(BotRow)
                .filter(BotRow.slug == spec.slug)
                .one_or_none()
            )
            if row is None:
                row = BotRow(
                    name=spec.name,
                    slug=spec.slug,
                    kind=spec.kind,
                    description=spec.description,
                    current_version=1,
                    spec_yaml=spec.to_yaml(),
                    status="draft",
                    annotations=spec.annotations,
                )
                if project_id:
                    row.project_id = project_id
                session.add(row)
                session.flush()
            existing = (
                session.query(BotVersion)
                .filter(BotVersion.spec_hash == sha)
                .filter(BotVersion.bot_id == row.id)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(BotVersion)
                .filter(BotVersion.bot_id == row.id)
                .count()
                + 1
            )
            version_row = BotVersion(
                bot_id=row.id,
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
            row.annotations = spec.annotations
            session.commit()
            return version_row.id
    except Exception:  # noqa: BLE001
        logger.exception("persist_spec failed for bot %s", spec.name)
        return None


def replay_spec_version(version_id: str) -> BotSpec:
    """Load a frozen spec back from ``bot_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_bots import BotVersion

    with SessionLocal() as session:
        row = session.query(BotVersion).filter(BotVersion.id == version_id).one_or_none()
        if row is None:
            raise KeyError(f"No bot spec version {version_id!r}")
        return BotSpec.model_validate(row.payload)


__all__ = [
    "add_spec",
    "get_bot_spec",
    "list_bot_specs",
    "persist_spec",
    "register_bot_spec",
    "reload_yaml_dir",
    "replay_spec_version",
]
