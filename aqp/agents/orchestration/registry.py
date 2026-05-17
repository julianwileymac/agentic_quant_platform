"""Discovery / lookup APIs for :class:`OrchestrationAdapter` subclasses.

Two indexes back this module:

1. The global one in :mod:`aqp.core.registry` (every adapter is
   registered there under ``kind="orchestration_adapter"`` so the
   existing browser sees them).
2. A local per-sub-kind shadow ``{sub_kind: {alias: class}}`` updated
   by the :class:`aqp.agents.orchestration.base.OrchestrationAdapterMeta`
   metaclass at class-definition time. This is what callers normally
   use: ``list_adapters("graph")`` returns only graph adapters.

The seven canonical sub-kinds are fixed in :data:`ADAPTER_KINDS`. New
sub-kinds may not be added without bumping
:data:`ADAPTER_KINDS_VERSION` so the Phase 5 studio dropdown stays
deterministic.
"""
from __future__ import annotations

from typing import Literal

ADAPTER_KINDS: tuple[str, ...] = (
    "graph",
    "crew",
    "debate",
    "fusion",
    "execution",
    "schedule",
    "studio",
)
"""Canonical sub-kinds for :class:`OrchestrationAdapter` implementations."""

ADAPTER_KINDS_VERSION = 1
"""Bump when :data:`ADAPTER_KINDS` changes — the studio reads this."""

OrchestrationAdapterKind = Literal[
    "graph",
    "crew",
    "debate",
    "fusion",
    "execution",
    "schedule",
    "studio",
]


# Shadow index: {sub_kind: {alias: class}} populated by the metaclass.
_ADAPTERS_BY_KIND: dict[str, dict[str, type]] = {kind: {} for kind in ADAPTER_KINDS}


def _record_adapter(kind: str, alias: str, cls: type) -> None:
    """Metaclass hook — adds ``cls`` to the per-sub-kind shadow index.

    Unknown sub-kinds are silently dropped so the registry never
    drifts past :data:`ADAPTER_KINDS`. The metaclass logs the
    rejection at DEBUG level for diagnostics.
    """
    if kind not in _ADAPTERS_BY_KIND:
        return
    _ADAPTERS_BY_KIND[kind][alias] = cls


def list_adapters(
    kind: OrchestrationAdapterKind | str | None = None,
) -> dict[str, type]:
    """Return ``{alias: class}`` for one sub-kind, or every adapter.

    Examples
    --------
    >>> list_adapters("graph")  # doctest: +SKIP
    {'LangGraphAdapter': <class '...'>}
    >>> list(list_adapters())  # doctest: +SKIP
    ['LangGraphAdapter', 'CrewProcessAdapter', ...]
    """
    if kind is None:
        out: dict[str, type] = {}
        for bucket in _ADAPTERS_BY_KIND.values():
            out.update(bucket)
        return out
    if kind not in _ADAPTERS_BY_KIND:
        raise KeyError(
            f"unknown orchestration adapter kind {kind!r}; "
            f"expected one of {ADAPTER_KINDS}"
        )
    return dict(_ADAPTERS_BY_KIND[kind])


def list_adapter_aliases(
    kind: OrchestrationAdapterKind | str | None = None,
) -> list[str]:
    """Sorted alias list for a sub-kind (or every adapter)."""
    return sorted(list_adapters(kind).keys())


def get_adapter(alias: str) -> type:
    """Return the adapter class registered under ``alias``.

    Looks through every sub-kind in the order declared by
    :data:`ADAPTER_KINDS`. Raises :class:`KeyError` when the alias is
    unknown so callers fail loudly instead of importing a stale shim.
    """
    for bucket in _ADAPTERS_BY_KIND.values():
        if alias in bucket:
            return bucket[alias]
    raise KeyError(
        f"unknown orchestration adapter alias {alias!r}; "
        f"registered: {sorted(list_adapters().keys())}"
    )


def adapter_kind_for(cls: type) -> str | None:
    """Return ``cls.adapter_kind`` or the inherited value."""
    return getattr(cls, "adapter_kind", None)


def describe_adapter_catalog() -> list[dict[str, object]]:
    """Return a JSON-friendly catalog used by the studio dropdown.

    Each entry comes from :meth:`OrchestrationAdapter.describe`.
    Sorted by ``(kind, alias)`` for stable output.
    """
    out: list[dict[str, object]] = []
    for kind in ADAPTER_KINDS:
        for alias in sorted(_ADAPTERS_BY_KIND[kind]):
            cls = _ADAPTERS_BY_KIND[kind][alias]
            describe = getattr(cls, "describe", None)
            if callable(describe):
                out.append(describe())
            else:
                out.append({"alias": alias, "kind": kind, "class": cls.__name__})
    return out


__all__ = [
    "ADAPTER_KINDS",
    "ADAPTER_KINDS_VERSION",
    "OrchestrationAdapterKind",
    "_record_adapter",
    "adapter_kind_for",
    "describe_adapter_catalog",
    "get_adapter",
    "list_adapter_aliases",
    "list_adapters",
]
