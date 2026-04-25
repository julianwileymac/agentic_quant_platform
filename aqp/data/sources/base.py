"""Base contract for rich data-source adapters.

Each concrete adapter (FRED, SEC, GDelt, ...) subclasses
:class:`DataSourceAdapter` and implements:

* :meth:`probe` — cheap health check used by the ``/sources/{name}/probe``
  endpoint and by Celery tasks before kicking off a long-running ingest.
* :meth:`fetch_metadata` — returns catalog-level information (available
  series, filings index, manifest slice) without pulling the heavy
  observations.
* :meth:`fetch_observations` — the workhorse. Returns a tidy
  :class:`pandas.DataFrame` and a lineage dict suitable for
  :func:`aqp.data.catalog.register_dataset_version`.

The legacy :class:`aqp.data.ingestion.BaseDataSource` contract (tidy
OHLCV bars only) is preserved unchanged; the adapters here are a
richer, optional addition layered on top.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.data.sources.domains import DataDomain


@dataclass
class IdentifierSpec:
    """A single identifier alias emitted by an adapter.

    Adapters return a list of these from
    :meth:`DataSourceAdapter.resolve_identifiers` so the
    :class:`aqp.data.sources.resolvers.identifiers.IdentifierResolver`
    can upsert them into the ``identifier_links`` table and link them
    back to the canonical :class:`Instrument` when possible.
    """

    scheme: str
    value: str
    entity_kind: str = "instrument"
    entity_id: str | None = None
    instrument_vt_symbol: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeResult:
    """Outcome of a cheap health check against a data source."""

    ok: bool
    message: str = ""
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, message: str = "ok", **details: Any) -> "ProbeResult":
        return cls(ok=True, message=message, details=dict(details))

    @classmethod
    def failure(cls, message: str, **details: Any) -> "ProbeResult":
        return cls(ok=False, message=message, details=dict(details))


@dataclass
class ObservationsResult:
    """Return value of :meth:`DataSourceAdapter.fetch_observations`."""

    data: pd.DataFrame
    lineage: dict[str, Any] = field(default_factory=dict)
    identifiers: list[IdentifierSpec] = field(default_factory=list)
    data_links: list[dict[str, Any]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.data is None or self.data.empty

    @property
    def row_count(self) -> int:
        return 0 if self.empty else int(len(self.data))


class DataSourceAdapter(ABC):
    """Uniform contract for rich, non-bar data sources.

    Concrete adapters declare their ``source_key`` (the ``data_sources.name``
    value they correspond to), their ``domain``, and a ``display_name``.
    Every other method has a sensible default or is explicitly abstract.
    """

    source_key: str = "unknown"
    display_name: str = "Unknown Data Source"
    domain: DataDomain = DataDomain.MARKET_BARS

    @abstractmethod
    def probe(self) -> ProbeResult:
        """Cheap health check: creds reachable, vendor endpoint up."""

    @abstractmethod
    def fetch_metadata(self, **kwargs: Any) -> dict[str, Any]:
        """Return catalog-level metadata (series list, filings index, ...)."""

    @abstractmethod
    def fetch_observations(self, **kwargs: Any) -> ObservationsResult:
        """Return tidy observations + lineage dict + identifier specs."""

    # ------------------------------------------------------------------
    # Default helpers — adapters may override.
    # ------------------------------------------------------------------

    def resolve_identifiers(self, row: dict[str, Any]) -> list[IdentifierSpec]:
        """Best-effort identifier extraction for a single row/record."""
        return []

    def capabilities(self) -> dict[str, Any]:
        """Return a dict summarising what the adapter can do.

        Merged into the ``data_sources.capabilities`` column when a
        :class:`~aqp.data.sources.registry.DataSource` row is upserted.
        """
        return {"domain": str(self.domain), "source_key": self.source_key}
