"""Layered configuration overlay (global > org > team > user > workspace > project).

Borrows the :func:`merge_dicts` semantics from vectorbt-pro
(:mod:`vectorbtpro.utils.config`) plus its ``atomic_dict`` and ``unsetkey``
escape hatches:

- Nested dicts merge recursively at every layer.
- Wrapping a value in :class:`AtomicDict` (or calling :func:`atomic_dict`)
  makes it replace the underlying value wholesale instead of merging.
- Setting a value to the :data:`UNSET` sentinel removes that key at the
  current layer.

The six layers compose in :data:`SCOPE_RESOLUTION_ORDER`
(``global < org < team < user < workspace < project``); the right-hand
value wins on conflict, which matches "most-specific scope wins".

Layer payloads are pulled from the :class:`ConfigOverlayRow` table by
``(scope_kind, scope_id, namespace)``. The global layer is the
:class:`Settings` baseline pulled via :func:`_global_layer`.
"""
from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable, Mapping

from aqp.config.defaults import (
    SCOPE_GLOBAL,
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_RESOLUTION_ORDER,
    SCOPE_TEAM,
    SCOPE_USER,
    SCOPE_WORKSPACE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Atomic-replace + unset sentinels (vbt-pro pattern)
# ---------------------------------------------------------------------------
class _UnsetSentinel:
    """Singleton sentinel meaning 'remove this key at the current layer'.

    Inspired by ``vectorbtpro.utils.config.unsetkey``. When a layer payload
    contains ``"foo": UNSET`` the merger drops ``"foo"`` from the running
    result rather than overwriting it with the sentinel.
    """

    _instance: "_UnsetSentinel | None" = None

    def __new__(cls) -> "_UnsetSentinel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "<UNSET>"

    def __bool__(self) -> bool:  # pragma: no cover - cosmetic
        return False


UNSET: _UnsetSentinel = _UnsetSentinel()
_UNSET_MARKER: str = "__unset__"


class AtomicDict(dict):
    """Dict subclass that opts out of recursive merging.

    Mirrors :class:`vectorbtpro.utils.config.atomic_dict`. When the merger
    encounters an :class:`AtomicDict` on either side of a merge, the value
    replaces the running entry instead of being merged element-wise. Use
    when an overlay needs to wholesale replace a sub-tree (for example,
    swapping out an entire LLM profile rather than overlaying individual
    fields).
    """


def atomic_dict(data: Mapping[str, Any] | None = None, /, **kwargs: Any) -> AtomicDict:
    """Construct an :class:`AtomicDict` from any mapping or kwargs."""
    if data is None:
        return AtomicDict(**kwargs)
    out = AtomicDict(dict(data))
    out.update(kwargs)
    return out


# ---------------------------------------------------------------------------
# Path-key resolution (vbt-pro ``get_pathlike_key`` style)
# ---------------------------------------------------------------------------
_PATH_TOKEN = re.compile(r"[^\.\[\]]+|\[\d+\]")


def _resolve_path(key: str | tuple[str, ...] | list[str]) -> tuple[str | int, ...]:
    """Tokenise ``"a.b[2].c"`` into ``("a", "b", 2, "c")``."""
    if isinstance(key, (tuple, list)):
        return tuple(_coerce_token(t) for t in key)
    if not isinstance(key, str):
        return (key,)
    tokens: list[str | int] = []
    for tok in _PATH_TOKEN.findall(key):
        if tok.startswith("[") and tok.endswith("]"):
            try:
                tokens.append(int(tok[1:-1]))
            except ValueError:
                tokens.append(tok[1:-1])
        else:
            tokens.append(tok)
    return tuple(tokens)


def _coerce_token(tok: Any) -> str | int:
    if isinstance(tok, int):
        return tok
    s = str(tok)
    if s.isdigit():
        return int(s)
    return s


def get_path(obj: Any, key: str | tuple[str, ...] | list[str], default: Any = None) -> Any:
    """Walk *obj* using a dotted/bracket path, returning *default* on miss.

    Mirrors vbt-pro's :func:`vectorbtpro.utils.search_.get_pathlike_key`.
    Supports both dict-key access and integer list indexing.
    """
    cur: Any = obj
    for tok in _resolve_path(key):
        try:
            if isinstance(tok, int):
                cur = cur[tok]
            elif isinstance(cur, Mapping):
                cur = cur[tok]
            elif hasattr(cur, "__getitem__"):
                cur = cur[tok]
            elif hasattr(cur, str(tok)):
                cur = getattr(cur, str(tok))
            else:
                return default
        except (KeyError, IndexError, TypeError, AttributeError):
            return default
    return cur


# ---------------------------------------------------------------------------
# Merge primitives (vbt-pro ``merge_dicts`` / ``flat_merge_dicts`` port)
# ---------------------------------------------------------------------------
def _normalise_unset(value: Any) -> Any:
    """Coerce the JSON-friendly ``"__unset__"`` literal to the sentinel."""
    if value is UNSET:
        return UNSET
    if isinstance(value, str) and value == _UNSET_MARKER:
        return UNSET
    return value


def _update_dict(target: dict, source: Mapping[str, Any], *, nested: bool) -> dict:
    """In-place merge of *source* into *target* with vbt-pro semantics."""
    for raw_key, raw_val in source.items():
        val = _normalise_unset(raw_val)
        if val is UNSET:
            target.pop(raw_key, None)
            continue
        if (
            nested
            and raw_key in target
            and isinstance(target[raw_key], Mapping)
            and isinstance(val, Mapping)
            and not isinstance(target[raw_key], AtomicDict)
            and not isinstance(val, AtomicDict)
        ):
            child = dict(target[raw_key])
            _update_dict(child, val, nested=nested)
            target[raw_key] = child
        else:
            if isinstance(val, AtomicDict):
                target[raw_key] = AtomicDict(val)
            elif isinstance(val, Mapping):
                target[raw_key] = dict(val)
            else:
                target[raw_key] = val
    return target


def merge_dicts(
    *dicts: Mapping[str, Any] | None,
    nested: bool = True,
    copy: bool = True,
) -> dict:
    """Merge multiple dicts left-to-right; later wins on conflict.

    ``nested=True`` recurses into child mappings (vbt-pro default). Wrap a
    value in :class:`AtomicDict` to opt out of recursion for that key.
    ``UNSET`` entries are stripped.

    Returns a fresh dict (deep-copied when ``copy=True``) so the input
    layers are never mutated.
    """
    if not dicts:
        return {}
    base: dict = {}
    for layer in dicts:
        if layer is None or not layer:
            continue
        snapshot = deepcopy(layer) if copy else dict(layer)
        _update_dict(base, snapshot, nested=nested)
    return base


def flat_merge_dicts(*dicts: Mapping[str, Any] | None, copy: bool = True) -> dict:
    """Shallow overlay — later layers replace whole values at the top level."""
    return merge_dicts(*dicts, nested=False, copy=copy)


# ---------------------------------------------------------------------------
# Global baseline (Settings → flat dict by namespace)
# ---------------------------------------------------------------------------
def _global_layer(namespace: str) -> dict[str, Any]:
    """Project the :class:`Settings` baseline into a per-namespace dict.

    Only keys whose Settings field name starts with ``{namespace}_`` are
    surfaced (with the prefix stripped). Returns ``{}`` for unknown
    namespaces so the caller's overlays are still merged on top.

    Example: ``_global_layer("llm")`` returns
    ``{"provider": settings.llm_provider, "model": settings.llm_model, ...}``.
    """
    try:
        from aqp.config.settings import settings
    except Exception:
        return {}
    prefix = f"{namespace}_"
    out: dict[str, Any] = {}
    try:
        fields = settings.model_dump()
    except Exception:
        return {}
    for key, value in fields.items():
        if key.startswith(prefix):
            stripped = key[len(prefix):]
            out[stripped] = value
    return out


# ---------------------------------------------------------------------------
# Overlay store (ConfigOverlayRow CRUD)
# ---------------------------------------------------------------------------
def _layer_for_scope(
    scope_kind: str, scope_id: str | None, namespace: str
) -> dict[str, Any]:
    """Pull a single overlay row from Postgres; return ``{}`` on miss/error."""
    if scope_kind == SCOPE_GLOBAL:
        return _global_layer(namespace)
    if not scope_id:
        return {}
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import ConfigOverlayRow

        with get_session() as session:
            row = (
                session.query(ConfigOverlayRow)
                .filter(
                    ConfigOverlayRow.scope_kind == scope_kind,
                    ConfigOverlayRow.scope_id == scope_id,
                    ConfigOverlayRow.namespace == namespace,
                )
                .one_or_none()
            )
            if row is None:
                return {}
            payload = row.payload or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    return {}
            return dict(payload) if isinstance(payload, Mapping) else {}
    except Exception:
        logger.debug(
            "Could not load overlay for %s:%s/%s",
            scope_kind, scope_id, namespace,
            exc_info=True,
        )
        return {}


def _ordered_scope_ids(context: Any) -> list[tuple[str, str | None]]:
    """Map a :class:`RequestContext` to ``[(scope_kind, scope_id), ...]``."""
    ids: list[tuple[str, str | None]] = []
    for kind in SCOPE_RESOLUTION_ORDER:
        if kind == SCOPE_GLOBAL:
            ids.append((SCOPE_GLOBAL, None))
            continue
        attr = f"{kind}_id"
        scope_id = getattr(context, attr, None) if context is not None else None
        if scope_id:
            ids.append((kind, scope_id))
    # Lab is *not* in the resolution order (treated as a sibling of project)
    # but if the context has a lab_id and not a project_id, treat lab as the
    # tail of the chain. This mirrors the "labs are notebooks under a
    # workspace, like projects but for research" framing.
    if context is not None and getattr(context, "lab_id", None) and not getattr(context, "project_id", None):
        ids.append((SCOPE_LAB, context.lab_id))
    return ids


def resolve_config(
    namespace: str,
    context: Any | None = None,
    fallback: Mapping[str, Any] | None = None,
    *,
    extra_layers: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve the effective config for ``namespace`` under ``context``.

    Walks the six layers in :data:`SCOPE_RESOLUTION_ORDER` (plus an optional
    lab layer when the context carries one without a project), pulls the
    overlay payload from the :class:`ConfigOverlayRow` table for each scope,
    and merges them into one dict using :func:`merge_dicts`.

    ``fallback`` is treated as the very bottom of the stack (below the
    global Settings layer) and is useful for code-supplied defaults that
    aren't expressed as Settings fields.

    ``extra_layers`` are appended to the very top of the stack (above
    project), useful for per-call overrides analogous to the
    ``override_options`` / ``override_setup_options`` slots in
    vbt-pro's :func:`register_chunkable`.
    """
    layers: list[Mapping[str, Any] | None] = []
    if fallback:
        layers.append(dict(fallback))
    for kind, scope_id in _ordered_scope_ids(context):
        layers.append(_layer_for_scope(kind, scope_id, namespace))
    if extra_layers:
        for el in extra_layers:
            if el:
                layers.append(el)
    return merge_dicts(*layers, nested=True)


# ---------------------------------------------------------------------------
# Mutating helpers — set / clear / get a single overlay row
# ---------------------------------------------------------------------------
def get_overlay(
    scope_kind: str, scope_id: str, namespace: str
) -> dict[str, Any] | None:
    """Return the raw overlay payload for one scope, or ``None`` if missing."""
    if scope_kind == SCOPE_GLOBAL:
        return _global_layer(namespace)
    layer = _layer_for_scope(scope_kind, scope_id, namespace)
    return layer or None


def set_overlay(
    scope_kind: str,
    scope_id: str,
    namespace: str,
    payload: Mapping[str, Any],
    *,
    updated_by: str | None = None,
    conflict: str = "last",
) -> str:
    """Insert or update one :class:`ConfigOverlayRow`.

    ``conflict`` mirrors vbt-pro's
    :class:`vectorbtpro.utils.config.Configured.resolve_merge_kwargs`
    semantics:

    - ``"last"`` (default): the new ``payload`` replaces the row (after
      deep-merging with the existing one).
    - ``"first"``: keep the existing row untouched if it already exists.
    - ``"error"``: raise ``ValueError`` on overlapping keys.

    Returns the row id.
    """
    if scope_kind == SCOPE_GLOBAL:
        raise ValueError("Cannot set overlay on the GLOBAL scope; edit Settings.")
    if not scope_id:
        raise ValueError(f"set_overlay requires a scope_id for scope_kind={scope_kind!r}")
    if scope_kind not in {SCOPE_ORG, SCOPE_TEAM, SCOPE_USER, SCOPE_WORKSPACE, SCOPE_PROJECT, SCOPE_LAB}:
        raise ValueError(f"Unknown scope_kind={scope_kind!r}")

    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import ConfigOverlayRow

    with get_session() as session:
        row = (
            session.query(ConfigOverlayRow)
            .filter(
                ConfigOverlayRow.scope_kind == scope_kind,
                ConfigOverlayRow.scope_id == scope_id,
                ConfigOverlayRow.namespace == namespace,
            )
            .one_or_none()
        )
        normalised = _normalise_payload(payload)
        if row is None:
            row = ConfigOverlayRow(
                scope_kind=scope_kind,
                scope_id=scope_id,
                namespace=namespace,
                payload=normalised,
                version=1,
                updated_by=updated_by,
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return row.id
        existing = dict(row.payload or {})
        if conflict == "first":
            return row.id
        if conflict == "error":
            overlap = set(existing) & set(normalised)
            if overlap:
                raise ValueError(
                    f"Overlay merge conflict on keys: {sorted(overlap)}"
                )
        merged = merge_dicts(existing, normalised, nested=True)
        row.payload = merged
        row.version = (row.version or 1) + 1
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
        session.flush()
        return row.id


def clear_overlay(
    scope_kind: str, scope_id: str, namespace: str
) -> bool:
    """Delete one overlay row. Returns ``True`` if a row was removed."""
    if scope_kind == SCOPE_GLOBAL:
        raise ValueError("Cannot clear the GLOBAL scope.")
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import ConfigOverlayRow

    with get_session() as session:
        row = (
            session.query(ConfigOverlayRow)
            .filter(
                ConfigOverlayRow.scope_kind == scope_kind,
                ConfigOverlayRow.scope_id == scope_id,
                ConfigOverlayRow.namespace == namespace,
            )
            .one_or_none()
        )
        if row is None:
            return False
        session.delete(row)
        return True


def _normalise_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert any non-JSON-serialisable values to strings before persisting."""
    try:
        json.dumps(payload, default=str)
        return dict(payload)
    except Exception:
        return json.loads(json.dumps(payload, default=str))


__all__ = [
    "AtomicDict",
    "UNSET",
    "atomic_dict",
    "clear_overlay",
    "flat_merge_dicts",
    "get_overlay",
    "get_path",
    "merge_dicts",
    "resolve_config",
    "set_overlay",
]
