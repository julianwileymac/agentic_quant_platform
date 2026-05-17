"""Base contract for entity-centric data products."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DataProductError(RuntimeError):
    """Raised when a data product cannot be assembled."""


@dataclass(slots=True)
class DataProvenance:
    """Where a data product's facts came from."""

    data_sources: list[str] = field(default_factory=list)
    dataset_versions: list[str] = field(default_factory=list)
    last_updated: datetime | None = None
    upstream_iceberg_tables: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "data_sources": list(self.data_sources),
            "dataset_versions": list(self.dataset_versions),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "upstream_iceberg_tables": list(self.upstream_iceberg_tables),
        }


@dataclass(slots=True)
class DataQuality:
    """Aggregate quality metrics for a data product."""

    reliability_score: float | None = None
    completeness: float | None = None
    freshness_seconds: float | None = None
    last_quality_check: datetime | None = None
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "reliability_score": self.reliability_score,
            "completeness": self.completeness,
            "freshness_seconds": self.freshness_seconds,
            "last_quality_check": (
                self.last_quality_check.isoformat() if self.last_quality_check else None
            ),
            "breakdown": dict(self.breakdown),
        }


@dataclass(slots=True)
class LineageBreadcrumb:
    """One step in the lineage trail of a data product."""

    transform_kind: str
    target_table_id: str | None
    timestamp: datetime
    summary: str | None = None
    actor: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "transform_kind": self.transform_kind,
            "target_table_id": self.target_table_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "summary": self.summary,
            "actor": self.actor,
        }


class BaseDataProduct(ABC):
    """Pre-aggregated, read-only context pack for one business entity.

    Subclasses set :attr:`product_kind` (eg. ``equity``, ``portfolio``,
    ``macro_series``) and implement :meth:`load`. Subclasses must NOT:

    - Read directly from Postgres bypassing the ORM (use
      :func:`aqp.persistence.db.get_session`)
    - Read raw Iceberg tables outside :mod:`aqp.data.iceberg_catalog`
    - Mutate any source table
    """

    product_kind: str = "base"

    def __init__(
        self,
        entity_id: str,
        *,
        as_of: datetime | None = None,
    ) -> None:
        if not entity_id:
            raise DataProductError("entity_id is required")
        self.entity_id = str(entity_id)
        self.as_of = as_of or datetime.utcnow()
        self._loaded = False
        self._payload: dict[str, Any] = {}
        self._provenance = DataProvenance()
        self._quality = DataQuality()
        self._lineage: list[LineageBreadcrumb] = []

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def to_context_pack(
        self, *, max_tokens: int | None = None, sections: list[str] | None = None
    ) -> dict[str, Any]:
        """Return an LLM-shaped dict snapshot.

        ``max_tokens`` lets the caller set a soft budget — sections are
        dropped from the bottom up if the payload would exceed it
        (greedy approximation). ``sections`` filters which top-level
        keys to include (eg. ``["instrument", "fundamentals"]``).
        """
        if not self._loaded:
            self._load_safe()
        payload = dict(self._payload)
        if sections:
            keep = set(sections)
            payload = {k: v for k, v in payload.items() if k in keep}
        envelope = {
            "product_kind": self.product_kind,
            "entity_id": self.entity_id,
            "as_of": self.as_of.isoformat(),
            "payload": payload,
            "provenance": self._provenance.to_json(),
            "quality": self._quality.to_json(),
            "lineage": [b.to_json() for b in self._lineage],
        }
        if max_tokens is not None:
            return _enforce_token_budget(envelope, max_tokens=max_tokens)
        return envelope

    def lineage(self) -> list[LineageBreadcrumb]:
        if not self._loaded:
            self._load_safe()
        return list(self._lineage)

    def provenance(self) -> DataProvenance:
        if not self._loaded:
            self._load_safe()
        return self._provenance

    def quality(self) -> DataQuality:
        if not self._loaded:
            self._load_safe()
        return self._quality

    # ------------------------------------------------------------------
    # Hooks subclasses override
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self) -> None:
        """Populate ``self._payload``, ``self._provenance``, etc.

        Subclasses set the attributes directly rather than returning a
        value so the base class can wrap the call with error handling.
        """

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def add_lineage(
        self,
        *,
        transform_kind: str,
        target_table_id: str | None = None,
        summary: str | None = None,
        actor: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self._lineage.append(
            LineageBreadcrumb(
                transform_kind=transform_kind,
                target_table_id=target_table_id,
                timestamp=timestamp or datetime.utcnow(),
                summary=summary,
                actor=actor,
            )
        )

    def add_provenance_source(self, name: str) -> None:
        if name and name not in self._provenance.data_sources:
            self._provenance.data_sources.append(name)

    def add_provenance_dataset(self, dataset_version_id: str) -> None:
        if (
            dataset_version_id
            and dataset_version_id not in self._provenance.dataset_versions
        ):
            self._provenance.dataset_versions.append(dataset_version_id)

    def add_iceberg_upstream(self, table_id: str) -> None:
        if (
            table_id
            and table_id not in self._provenance.upstream_iceberg_tables
        ):
            self._provenance.upstream_iceberg_tables.append(table_id)

    def set_quality(
        self,
        *,
        reliability_score: float | None = None,
        completeness: float | None = None,
        freshness_seconds: float | None = None,
        breakdown: dict[str, Any] | None = None,
    ) -> None:
        if reliability_score is not None:
            self._quality.reliability_score = float(reliability_score)
        if completeness is not None:
            self._quality.completeness = float(completeness)
        if freshness_seconds is not None:
            self._quality.freshness_seconds = float(freshness_seconds)
        if breakdown:
            merged = dict(self._quality.breakdown)
            merged.update(breakdown)
            self._quality.breakdown = merged
        self._quality.last_quality_check = datetime.utcnow()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_safe(self) -> None:
        try:
            self.load()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "data product %s.load failed for entity_id=%s",
                self.__class__.__name__,
                self.entity_id,
            )
            self._payload = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            self._loaded = True


# ---------------------------------------------------------------------------
# Token-budget approximation
# ---------------------------------------------------------------------------


def _enforce_token_budget(
    envelope: dict[str, Any], *, max_tokens: int
) -> dict[str, Any]:
    """Greedy token-budget approximation by JSON character size.

    Real tokenizers vary; for AQP context-pack purposes we approximate
    1 token = 4 characters and drop sections from the payload (least
    important first) until the envelope fits.
    """
    if max_tokens <= 0:
        return envelope
    budget_chars = max_tokens * 4
    serialized = _safe_json_dumps(envelope)
    if len(serialized) <= budget_chars:
        return envelope
    # Order to keep when truncating: instrument > quality > provenance >
    # everything else > lineage. Drop from the bottom of "everything
    # else" first.
    payload = dict(envelope.get("payload") or {})
    keep_order = [
        "instrument",
        "snapshot",
        "fundamentals",
        "ratios",
        "identifiers",
        "news",
        "regulatory",
        "options",
        "macro",
        "positions",
        "fills",
        "risk",
    ]
    ordered_keys = [k for k in keep_order if k in payload] + [
        k for k in payload if k not in keep_order
    ]
    while ordered_keys:
        dropped = ordered_keys.pop()
        payload.pop(dropped, None)
        envelope["payload"] = payload
        envelope.setdefault("truncated_sections", []).append(dropped)
        serialized = _safe_json_dumps(envelope)
        if len(serialized) <= budget_chars:
            return envelope
    # Last resort: drop lineage detail.
    envelope["lineage"] = envelope.get("lineage", [])[:1]
    return envelope


def _safe_json_dumps(obj: Any) -> str:
    try:
        import json

        return json.dumps(obj, default=str)
    except Exception:  # noqa: BLE001
        return str(obj)


__all__ = [
    "BaseDataProduct",
    "DataProductError",
    "DataProvenance",
    "DataQuality",
    "LineageBreadcrumb",
]
