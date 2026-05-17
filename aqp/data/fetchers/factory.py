"""Data extractor factory.

Codifies the **Factory pattern** the architectural blueprint calls
out: a single :class:`DataExtractorFactory` that hands back fully
constructed :class:`aqp.data.fetchers.base.Fetcher` (or generic
:class:`SourceNode`) instances based on a runtime alias / configuration
dict, eliminating brittle ``if/elif`` blocks scattered through
ingestion / API code.

The factory is a thin orchestration layer over
:func:`aqp.data.engine.registry.build_node` plus
:func:`aqp.data.sources.registry.upsert_data_source` — the heavy
lifting (registration, discovery) lives in those modules; the factory
just exposes a clean ``create(...)`` / ``capabilities(...)`` /
``introspect(...)`` API for the UI, MCP tools, and tests.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from aqp.data.engine.nodes import NodeKind
from aqp.data.engine.registry import (
    build_node,
    get_node_class,
    list_nodes_by_kind,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExtractorCapabilities:
    """Capabilities advertised for a registered fetcher / source node.

    Read by the Manifest Builder UI, the DataMCP tool catalog, and
    docs generation. Values are coarse — fine-grained negotiation
    happens at the ``Fetcher.fetch`` level.
    """

    name: str
    kind: str
    description: str = ""
    tags: tuple[str, ...] = ()
    module: str = ""
    class_name: str = ""
    capabilities: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    requires_auth: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class DataExtractorFactory:
    """Single entry point for instantiating data extractors.

    .. code-block:: python

        factory = DataExtractorFactory()
        fetcher = factory.create("source.alpha_vantage", symbol="SPY.NASDAQ")
        for batch in fetcher.fetch():
            ...

    The factory deliberately doesn't cache instances — extractor state
    (rate-limit buckets, cursor position, retry counters) is per-call
    and must not leak across invocations.
    """

    def __init__(self) -> None:
        # No state today, but kept as a class so that future capability
        # introspection (e.g. live probing) can persist short-lived caches.
        pass

    # ---------------------------------------------------------------- create

    def create(self, source_kind: str, /, **kwargs: Any) -> Any:
        """Instantiate a fetcher / source node from its registered alias.

        ``source_kind`` is the engine alias (eg. ``source.alpha_vantage``,
        ``source.cfpb``). ``kwargs`` are forwarded to the node
        constructor — invalid kwargs raise the underlying ``TypeError``
        from the constructor so misconfigured manifests surface loudly.
        """
        if not source_kind:
            raise ValueError("source_kind is required")
        return build_node(source_kind, kwargs=dict(kwargs))

    def get_class(self, source_kind: str) -> type:
        """Return the class registered under ``source_kind`` without constructing."""
        return get_node_class(source_kind)

    # -------------------------------------------------------- introspection

    def list_extractors(self, *, kind: NodeKind | str | None = None) -> list[ExtractorCapabilities]:
        """Return capability metadata for every registered fetcher.

        ``kind`` filters by node kind (``source``, ``transform``,
        ``sink``); when omitted, all source nodes are returned.
        """
        target_kind = kind or NodeKind.SOURCE
        rows = list_nodes_by_kind(target_kind)
        out: list[ExtractorCapabilities] = []
        for row in rows:
            cls = _safe_get_class(str(row.get("name") or ""))
            out.append(_build_capabilities(row, cls))
        return out

    def capabilities(self, source_kind: str) -> ExtractorCapabilities:
        """Return capabilities for a single registered alias."""
        cls = _safe_get_class(source_kind)
        rows = list_nodes_by_kind(NodeKind.SOURCE)
        meta = next((r for r in rows if r.get("name") == source_kind), {"name": source_kind, "kind": "source"})
        return _build_capabilities(meta, cls)


def _safe_get_class(name: str) -> type | None:
    if not name:
        return None
    try:
        return get_node_class(name)
    except KeyError:
        return None


def _build_capabilities(meta: dict[str, Any], cls: type | None) -> ExtractorCapabilities:
    capabilities: list[str] = []
    domains: list[str] = []
    requires_auth = False
    if cls is not None:
        adv = getattr(cls, "advertised_capabilities", None)
        if adv:
            try:
                capabilities = [str(c) for c in adv]
            except Exception:  # noqa: BLE001
                capabilities = []
        adv_domains = getattr(cls, "advertised_domains", None)
        if adv_domains:
            try:
                domains = [str(d) for d in adv_domains]
            except Exception:  # noqa: BLE001
                domains = []
        requires_auth = bool(getattr(cls, "requires_auth", False))
    return ExtractorCapabilities(
        name=str(meta.get("name") or ""),
        kind=str(meta.get("kind") or "source"),
        description=str(meta.get("description") or ""),
        tags=tuple(meta.get("tags") or ()),
        module=str(meta.get("module") or (cls.__module__ if cls else "")),
        class_name=str(meta.get("class_name") or (cls.__name__ if cls else "")),
        capabilities=capabilities,
        domains=domains,
        requires_auth=requires_auth,
    )


_default_factory = DataExtractorFactory()


def get_default_factory() -> DataExtractorFactory:
    """Return the process-wide default factory."""
    return _default_factory


__all__ = [
    "DataExtractorFactory",
    "ExtractorCapabilities",
    "get_default_factory",
]
