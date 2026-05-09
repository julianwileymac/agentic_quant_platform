"""Flow + spec registry for the analysis umbrella.

Two responsibilities, both modelled on :mod:`aqp.rl.registry`:

1. **Flow registry** — :func:`register_analysis_flow` decorator
   captures a :class:`FlowDescriptor` for every concrete analysis
   function. The lab UI (``GET /analysis/flows``) and the runtime
   (`AnalysisRuntime.dispatch`) both read from this single dict.
2. **Spec registry** — :func:`add_spec` / :func:`get_analysis_spec` /
   :func:`list_analysis_specs` mirror the in-memory side of
   :mod:`aqp.bots.registry` so YAML specs under
   ``configs/analysis/`` auto-load on first lookup.

:func:`persist_spec` snapshots an :class:`AnalysisSpec` into
``analysis_spec_versions`` (idempotent by SHA-256 hash). Returns the
new version row id, or ``None`` when Postgres is unreachable so the
runtime can keep going on a laptop without a DB.
"""
from __future__ import annotations

import functools
import logging
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from aqp.analysis.base import (
    FlowContext,
    FlowDescriptor,
    FlowParams,
    FlowResult,
    FlowRunner,
    FlowSchema,
)
from aqp.analysis.spec import AnalysisSpec, load_specs_from_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Flow registry
# ---------------------------------------------------------------------------

FLOW_REGISTRY: dict[str, FlowDescriptor] = {}
"""Process-wide flow registry, keyed by namespaced flow name."""

_FLOW_LOCK = threading.RLock()


def register_analysis_flow(
    *,
    name: str,
    namespace: str,
    label: str,
    description: str,
    params_model: type[FlowParams],
    tags: Iterable[str] = (),
    requires_dataset: bool = True,
    output_kind: str = "table",
    optional_dependencies: Iterable[str] = (),
    output_namespace: str | None = None,
):
    """Decorator that registers an analysis flow.

    The ``name`` MUST be namespaced (``"<namespace>.<flow>"`` like
    ``"distribution.shapiro_wilk"``). Re-registration with the same
    name overwrites — this matches the ``aqp.core.registry.register``
    semantics so hot-reload during development works.
    """

    def decorator(runner: FlowRunner) -> FlowRunner:
        if not name or "." not in name:
            raise ValueError(
                f"register_analysis_flow: name must be 'namespace.flow', got {name!r}"
            )
        descriptor = FlowDescriptor(
            name=name,
            namespace=namespace,
            label=label,
            description=description,
            runner=runner,
            params_model=params_model,
            tags=tuple(tags),
            requires_dataset=bool(requires_dataset),
            output_kind=output_kind,
            optional_dependencies=tuple(optional_dependencies),
            output_namespace=output_namespace,
        )
        with _FLOW_LOCK:
            FLOW_REGISTRY[name] = descriptor
        # Stash the descriptor on the function so callers can introspect
        # without a registry round-trip.
        runner.__analysis_flow__ = descriptor  # type: ignore[attr-defined]

        @functools.wraps(runner)
        def wrapped(df: Any, params: FlowParams, ctx: FlowContext) -> FlowResult:
            return runner(df, params, ctx)

        wrapped.__analysis_flow__ = descriptor  # type: ignore[attr-defined]
        return wrapped

    return decorator


def list_analysis_flows() -> list[FlowSchema]:
    """JSON-friendly list of every registered flow's schema."""
    with _FLOW_LOCK:
        descriptors = list(FLOW_REGISTRY.values())
    return [d.schema() for d in sorted(descriptors, key=lambda d: d.name)]


def resolve_flow(name: str) -> FlowDescriptor:
    """Look up a flow descriptor by namespaced name. Raises ``KeyError``."""
    with _FLOW_LOCK:
        if name in FLOW_REGISTRY:
            return FLOW_REGISTRY[name]
    raise KeyError(f"No analysis flow registered under {name!r}")


def run_flow(
    name: str,
    df: Any,
    params: FlowParams | dict[str, Any],
    ctx: FlowContext | None = None,
) -> FlowResult:
    """Execute a registered flow with raw / dict params.

    Centralises the params validation step so both REST handlers and
    Celery tasks share one path.
    """
    desc = resolve_flow(name)
    if isinstance(params, dict):
        params_obj = desc.params_model.model_validate(params)
    else:
        params_obj = params
    fctx = ctx or FlowContext()
    return desc.runner(df, params_obj, fctx)


# ---------------------------------------------------------------------------
# Spec registry (in-memory + YAML autoscan)
# ---------------------------------------------------------------------------

_SPEC_REGISTRY: dict[str, AnalysisSpec] = {}
_SPEC_LOCK = threading.RLock()
_DIR_SCANNED: set[str] = set()
_DEFAULT_DIR = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "analysis"
)


def add_spec(spec: AnalysisSpec) -> None:
    """Register an in-memory analysis spec."""
    with _SPEC_LOCK:
        _index_spec(spec)


def _index_spec(spec: AnalysisSpec) -> None:
    if spec.slug:
        _SPEC_REGISTRY[spec.slug] = spec
    if spec.name and spec.name != spec.slug:
        _SPEC_REGISTRY[spec.name] = spec


def list_analysis_specs() -> list[AnalysisSpec]:
    _ensure_yaml_scan()
    with _SPEC_LOCK:
        seen: set[int] = set()
        out: list[AnalysisSpec] = []
        for spec in _SPEC_REGISTRY.values():
            if id(spec) in seen:
                continue
            seen.add(id(spec))
            out.append(spec)
        return out


def get_analysis_spec(name_or_slug: str) -> AnalysisSpec:
    with _SPEC_LOCK:
        if name_or_slug in _SPEC_REGISTRY:
            return _SPEC_REGISTRY[name_or_slug]
    _ensure_yaml_scan()
    with _SPEC_LOCK:
        if name_or_slug in _SPEC_REGISTRY:
            return _SPEC_REGISTRY[name_or_slug]
    raise KeyError(f"No analysis spec registered under {name_or_slug!r}")


def _ensure_yaml_scan() -> None:
    key = str(_DEFAULT_DIR.resolve())
    with _SPEC_LOCK:
        if key in _DIR_SCANNED:
            return
        _DIR_SCANNED.add(key)
    if not _DEFAULT_DIR.exists():
        return
    for spec in load_specs_from_dir(str(_DEFAULT_DIR)):
        with _SPEC_LOCK:
            if spec.slug and spec.slug not in _SPEC_REGISTRY:
                _SPEC_REGISTRY[spec.slug] = spec
            if spec.name and spec.name not in _SPEC_REGISTRY:
                _SPEC_REGISTRY[spec.name] = spec


def reload_yaml_dir(path: str | Path | None = None) -> int:
    target = Path(path) if path else _DEFAULT_DIR
    n = 0
    for spec in load_specs_from_dir(str(target)):
        with _SPEC_LOCK:
            _index_spec(spec)
        n += 1
    return n


# ---------------------------------------------------------------------------
# Persistence (analysis_specs / analysis_spec_versions)
# ---------------------------------------------------------------------------


def persist_spec(
    spec: AnalysisSpec, *, project_id: str | None = None
) -> str | None:
    """Snapshot ``spec`` into ``analysis_spec_versions`` (idempotent by hash).

    Returns the version row id, or ``None`` if Postgres is unavailable —
    matches the bot/agent/RL ``persist_spec`` behaviour so the runtime
    keeps going with no persistence layer.
    """
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_analysis import (
            AnalysisSpec as SpecRow,
            AnalysisSpecVersion,
        )
    except Exception:  # pragma: no cover
        logger.debug("Analysis persistence unavailable", exc_info=True)
        return None
    sha = spec.snapshot_hash()
    payload = spec.model_dump(mode="json")
    try:
        with SessionLocal() as session:
            row = (
                session.query(SpecRow)
                .filter(SpecRow.slug == spec.slug)
                .one_or_none()
            )
            if row is None:
                row = SpecRow(
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
                session.query(AnalysisSpecVersion)
                .filter(AnalysisSpecVersion.spec_hash == sha)
                .filter(AnalysisSpecVersion.spec_id == row.id)
                .one_or_none()
            )
            if existing is not None:
                return existing.id
            next_version = (
                session.query(AnalysisSpecVersion)
                .filter(AnalysisSpecVersion.spec_id == row.id)
                .count()
                + 1
            )
            version_row = AnalysisSpecVersion(
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
        logger.exception("persist_spec failed for analysis spec %s", spec.name)
        return None


def replay_spec_version(version_id: str) -> AnalysisSpec:
    """Load a frozen :class:`AnalysisSpec` back from ``analysis_spec_versions``."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_analysis import AnalysisSpecVersion

    with SessionLocal() as session:
        row = (
            session.query(AnalysisSpecVersion)
            .filter(AnalysisSpecVersion.id == version_id)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"No analysis spec version {version_id!r}")
        return AnalysisSpec.model_validate(row.payload)


__all__ = [
    "FLOW_REGISTRY",
    "add_spec",
    "get_analysis_spec",
    "list_analysis_flows",
    "list_analysis_specs",
    "persist_spec",
    "register_analysis_flow",
    "reload_yaml_dir",
    "replay_spec_version",
    "resolve_flow",
    "run_flow",
]
