"""Node registry for the unified data engine.

Mirrors :mod:`aqp.core.registry` style — a global ``{name -> class}``
mapping plus a kind-bucket index. Decorate a node class with
``@register_node("source.alpha_vantage")`` and the engine can build
instances from a manifest entry like::

    {"name": "source.alpha_vantage", "kwargs": {"symbol": "SPY.NASDAQ"}}

Nodes self-register at import time. The fetcher / transform / sink
modules under :mod:`aqp.data.fetchers` import this module to register
themselves.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from typing import Any

from aqp.data.engine.nodes import NodeKind

logger = logging.getLogger(__name__)


_node_registry: dict[str, type] = {}
_node_kind_index: dict[NodeKind, dict[str, type]] = {
    NodeKind.SOURCE: {},
    NodeKind.TRANSFORM: {},
    NodeKind.SINK: {},
}
_node_meta: dict[str, dict[str, Any]] = {}
_default_nodes_imported = False


def register_node(
    name: str,
    *,
    kind: NodeKind | str | None = None,
    description: str | None = None,
    tags: tuple[str, ...] = (),
) -> Callable[[type], type]:
    """Register a node class under ``name``.

    ``kind`` is auto-detected from the class hierarchy (``SourceNode``,
    ``TransformNode``, ``SinkNode``) when not provided. ``tags`` and
    ``description`` are stored for UI surfacing in the Manifest Builder.
    """

    def _wrap(cls: type) -> type:
        from aqp.data.engine.nodes import SinkNode, SourceNode, TransformNode

        node_kind: NodeKind | None
        if isinstance(kind, NodeKind):
            node_kind = kind
        elif isinstance(kind, str):
            try:
                node_kind = NodeKind(kind)
            except ValueError:
                node_kind = None
        else:
            node_kind = None

        if node_kind is None:
            if issubclass(cls, SourceNode):
                node_kind = NodeKind.SOURCE
            elif issubclass(cls, SinkNode):
                node_kind = NodeKind.SINK
            elif issubclass(cls, TransformNode):
                node_kind = NodeKind.TRANSFORM
            else:
                raise TypeError(
                    f"register_node({name!r}): cannot infer NodeKind for {cls!r}"
                )

        if name in _node_registry and _node_registry[name] is not cls:
            logger.debug("Replacing node registration for %s", name)
        _node_registry[name] = cls
        _node_kind_index.setdefault(node_kind, {})[name] = cls
        _node_meta[name] = {
            "name": name,
            "kind": node_kind.value,
            "description": description or (cls.__doc__ or "").strip().splitlines()[0]
            if (description or cls.__doc__)
            else "",
            "tags": tuple(tags),
            "module": cls.__module__,
            "class_name": cls.__name__,
        }
        return cls

    return _wrap


def get_node_class(name: str) -> type:
    """Return the registered class for ``name``.

    Falls back to dotted-import (``module.ClassName``) when the alias
    is not registered, mirroring :func:`aqp.core.registry.resolve`.
    """
    if name in _node_registry:
        return _node_registry[name]
    _ensure_default_nodes_imported()
    if name in _node_registry:
        return _node_registry[name]
    if "." in name:
        module_path, cls_name = name.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:  # pragma: no cover - import error path
            raise KeyError(f"unknown node {name!r}: {exc}") from exc
        if not hasattr(mod, cls_name):
            raise KeyError(f"unknown node {name!r}")
        return getattr(mod, cls_name)
    raise KeyError(f"unknown node {name!r}")


def list_nodes() -> list[dict[str, Any]]:
    """Return metadata for every registered node, sorted by name."""
    _ensure_default_nodes_imported()
    return [dict(_node_meta[name]) for name in sorted(_node_registry)]


def list_nodes_by_kind(kind: NodeKind | str) -> list[dict[str, Any]]:
    """Return metadata for every registered node of a given kind."""
    _ensure_default_nodes_imported()
    if isinstance(kind, str):
        kind = NodeKind(kind)
    rows = []
    for name in sorted(_node_kind_index.get(kind, {})):
        rows.append(dict(_node_meta[name]))
    return rows


def build_node(name: str, kwargs: dict[str, Any] | None = None) -> Any:
    """Instantiate a node from a registry alias and a kwargs dict."""
    cls = get_node_class(name)
    return cls(**(kwargs or {}))


def _ensure_default_nodes_imported() -> None:
    global _default_nodes_imported
    if _default_nodes_imported:
        return
    import_default_nodes()
    _default_nodes_imported = True


def import_default_nodes() -> None:
    """Import the bundled fetcher modules so their nodes self-register.

    Best-effort: missing optional deps (Dask/Ray/Kafka) are logged and
    skipped. Safe to call multiple times.
    """
    global _default_nodes_imported
    modules = (
        "aqp.data.fetchers",
        "aqp.data.fetchers.api",
        "aqp.data.fetchers.url",
        "aqp.data.fetchers.local",
        "aqp.data.fetchers.stream",
        "aqp.data.fetchers.transforms",
        "aqp.data.fetchers.sinks",
    )
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - best-effort registration
            logger.debug("import_default_nodes: %s skipped (%s)", mod, exc)
    _default_nodes_imported = True


__all__ = [
    "build_node",
    "get_node_class",
    "import_default_nodes",
    "list_nodes",
    "list_nodes_by_kind",
    "register_node",
]
