"""Unified source library for the AQP data engine.

This package owns every fetcher (API / URL / local / stream) plus the
shared transform and sink nodes used by manifests. Each module
self-registers via :func:`aqp.data.engine.register_node` at import
time, and seeds the ``data_sources`` table via
:func:`aqp.data.sources.registry.upsert_data_source` when a row isn't
already present.

Importing the top-level package eagerly imports the bundled fetcher
modules so the registry is fully populated. Optional deps (Dask,
Ray, Kafka, S3, GCS, Azure) are lazily imported by individual
fetchers and degrade gracefully when missing.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any

from aqp.data.fetchers.api import akshare_ohlcv, yfinance  # noqa: F401  registration
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    FetcherResult,
    Pagination,
    RateLimit,
    RetryPolicy,
    SourceLineage,
    register_source_fetcher,
)
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin

logger = logging.getLogger(__name__)


def _import_default_modules() -> None:
    """Eagerly import every bundled fetcher / transform / sink module.

    Best-effort: a missing optional dependency is logged at DEBUG and
    skipped so the registry still loads partially.
    """
    import importlib

    candidates = (
        "aqp.data.fetchers.transforms",
        "aqp.data.fetchers.sinks",
        "aqp.data.fetchers.local",
        "aqp.data.fetchers.url",
        "aqp.data.fetchers.api",
        "aqp.data.fetchers.stream",
    )
    for mod in candidates:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.debug("fetcher subpackage %s skipped: %s", mod, exc)


# Trigger registration on first import.
_import_default_modules()


def _source_node_rows() -> list[dict[str, Any]]:
    from aqp.data.engine.registry import list_nodes

    return [
        dict(row)
        for row in list_nodes()
        if str(row.get("name", "")).startswith("source.")
    ]


def get_loader_registry() -> dict[str, type[Fetcher]]:
    """Return a dynamic typed view over registered ``source.*`` nodes."""
    from aqp.data.engine.registry import get_node_class

    out: dict[str, type[Fetcher]] = {}
    for row in _source_node_rows():
        name = str(row.get("name", ""))
        if not name:
            continue
        try:
            cls = get_node_class(name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LOADER_REGISTRY skipped %s (%s)", name, exc)
            continue
        if isinstance(cls, type) and issubclass(cls, Fetcher):
            out[name] = cls
    return out


class _LoaderRegistryView(Mapping[str, type[Fetcher]]):
    def __getitem__(self, key: str) -> type[Fetcher]:
        return get_loader_registry()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(get_loader_registry())

    def __len__(self) -> int:
        return len(get_loader_registry())

    def __repr__(self) -> str:
        return repr(get_loader_registry())


LOADER_REGISTRY: Mapping[str, type[Fetcher]] = _LoaderRegistryView()


__all__ = [
    "Fetcher",
    "FabricFetcherMixin",
    "FetcherCapability",
    "FetcherKind",
    "FetcherResult",
    "LOADER_REGISTRY",
    "Pagination",
    "RateLimit",
    "RetryPolicy",
    "SourceLineage",
    "get_loader_registry",
    "register_source_fetcher",
]
