"""Terraform stack registry — discover, load, and persist :class:`TerraformStackSpec`.

Mirrors :mod:`aqp.bots.registry` and :mod:`aqp.agents.registry`:

- ``@register_terraform_spec("dual-region-eks")(TerraformStackSpec(...))``
  decorates code-loaded specs.
- YAML specs under ``aqp_platform/configs/terraform/`` auto-load on first lookup.
- :func:`persist_spec` writes a new immutable
  :class:`TerraformStackSpecVersion` row whenever the SHA-256 hash
  changes (AGENTS rule 43).

The registry is process-local + thread-safe; reload happens lazily so
the AQP API doesn't pay a YAML scan tax on every cold boot.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from aqp.terraform.spec import TerraformStackSpec, load_specs_from_dir

logger = logging.getLogger(__name__)


_REGISTRY: dict[str, TerraformStackSpec] = {}
_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "terraform"
)


# ---------------------------------------------------------------------------
# Decorator / in-memory registration
# ---------------------------------------------------------------------------


def register_terraform_spec(name: str | None = None):
    """Decorator: register a :class:`TerraformStackSpec` constructor / instance."""

    def decorator(target):
        spec = (
            target()
            if callable(target) and not isinstance(target, TerraformStackSpec)
            else target
        )
        if not isinstance(spec, TerraformStackSpec):
            raise TypeError(
                f"register_terraform_spec expects TerraformStackSpec, got {type(spec).__name__}"
            )
        with _LOCK:
            if name:
                _REGISTRY[name] = spec
            _index_spec(spec)
        return target

    return decorator


def add_spec(spec: TerraformStackSpec) -> None:
    """Register an in-memory spec without going through a decorator."""
    with _LOCK:
        _index_spec(spec)


def _index_spec(spec: TerraformStackSpec) -> None:
    if spec.slug:
        _REGISTRY[spec.slug] = spec
    if spec.name and spec.name != spec.slug:
        _REGISTRY[spec.name] = spec


def list_terraform_specs() -> list[TerraformStackSpec]:
    _ensure_yaml_scan()
    with _LOCK:
        seen: set[int] = set()
        out: list[TerraformStackSpec] = []
        for spec in _REGISTRY.values():
            if id(spec) in seen:
                continue
            seen.add(id(spec))
            out.append(spec)
        return out


def get_terraform_spec(name_or_slug: str) -> TerraformStackSpec:
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    _ensure_yaml_scan()
    with _LOCK:
        if name_or_slug in _REGISTRY:
            return _REGISTRY[name_or_slug]
    raise KeyError(f"No terraform spec registered under {name_or_slug!r}")


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
    """Re-read all YAML specs under ``path`` (or the default dir)."""
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_specs_from_dir(str(target)):
        with _LOCK:
            _index_spec(spec)
        n += 1
    return n


# ---------------------------------------------------------------------------
# Hash-locked persistence (AGENTS rule 43)
# ---------------------------------------------------------------------------


def persist_spec(
    spec: TerraformStackSpec,
    *,
    project_id: str | None = None,
    payload_hcl: str | None = None,
) -> str | None:
    """Snapshot ``spec`` into ``terraform_stack_spec_versions`` (idempotent by hash).

    Mirrors :func:`aqp.bots.registry.persist_spec`:

    1. Upserts the logical :class:`TerraformStackSpecRow` by
       ``(project_id, slug)``.
    2. Returns the version row id if a row with the same
       ``spec_hash`` already exists; otherwise inserts a new
       immutable :class:`TerraformStackSpecVersion` row and bumps
       :attr:`TerraformStackSpecRow.current_version`.

    The optional ``payload_hcl`` argument lets the caller stash the
    rendered HCL on the version row for diff / replay without
    re-running the Jinja2 codegen.

    Returns ``None`` if Postgres is unavailable so the runtime can
    keep going without persistence (matches the bots / agents path).
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_terraform import (
            TerraformStackSpecRow,
            TerraformStackSpecVersion,
        )
    except Exception:  # pragma: no cover
        logger.debug("Terraform persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = (
                session.query(TerraformStackSpecRow)
                .filter(TerraformStackSpecRow.slug == spec.slug)
                .one_or_none()
            )
            if row is None:
                row = TerraformStackSpecRow(
                    slug=spec.slug,
                    name=spec.name,
                    module_kind=spec.module_kind,
                    description=spec.description,
                    current_version=1,
                    annotations=spec.annotations,
                )
                if project_id:
                    row.project_id = project_id
                if spec.workspace_id:
                    row.workspace_id = spec.workspace_id
                session.add(row)
                session.flush()
            existing = (
                session.query(TerraformStackSpecVersion)
                .filter(TerraformStackSpecVersion.spec_hash == sha)
                .filter(TerraformStackSpecVersion.spec_id == row.id)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(TerraformStackSpecVersion)
                .filter(TerraformStackSpecVersion.spec_id == row.id)
                .count()
                + 1
            )
            version_row = TerraformStackSpecVersion(
                spec_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload_json=payload,
                payload_hcl=payload_hcl,
            )
            session.add(version_row)
            row.current_version = next_version
            row.module_kind = spec.module_kind
            row.name = spec.name
            row.description = spec.description
            row.annotations = spec.annotations
            session.commit()
            return version_row.id
    except Exception:  # noqa: BLE001
        logger.exception(
            "persist_spec failed for terraform stack %s", spec.name
        )
        return None


def replay_spec_version(version_id: str) -> TerraformStackSpec:
    """Load a frozen spec back from ``terraform_stack_spec_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_terraform import TerraformStackSpecVersion

    with SessionLocal() as session:
        row = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.id == version_id)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"No terraform spec version {version_id!r}")
        return TerraformStackSpec.model_validate(row.payload_json)


__all__ = [
    "add_spec",
    "get_terraform_spec",
    "list_terraform_specs",
    "persist_spec",
    "register_terraform_spec",
    "reload_yaml_dir",
    "replay_spec_version",
]
