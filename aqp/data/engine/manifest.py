"""Pydantic models for declarative pipeline manifests.

A :class:`PipelineManifest` is the JSON/YAML shape that the
``/data/ingest`` Manifest Builder UI emits and that the Dagster code
location reads to materialize assets dynamically. The manifest is the
one place where compute backend, source, transforms, sink, partitions,
and scheduling live together.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComputeBackendKind(str, enum.Enum):
    """Compute backend selector for a pipeline."""

    AUTO = "auto"
    LOCAL = "local"
    DASK = "dask"
    RAY = "ray"


class NodeSpec(BaseModel):
    """One node entry in a pipeline manifest.

    ``name`` is the registry alias (``source.alpha_vantage``,
    ``transform.arrow_select``, ``sink.iceberg``). ``kwargs`` is the
    per-node config that gets ``**`` -unpacked into the constructor.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Registered node alias")
    kwargs: dict[str, Any] = Field(default_factory=dict)
    label: str | None = Field(
        default=None, description="Optional human label (UI only)"
    )
    enabled: bool = Field(default=True)


class ComputeSpec(BaseModel):
    """Compute backend selection for a pipeline run."""

    model_config = ConfigDict(extra="forbid")

    backend: ComputeBackendKind = Field(default=ComputeBackendKind.AUTO)
    chunk_rows: int = Field(default=50_000, ge=1)
    max_concurrent_pipelines: int = Field(default=1, ge=1)
    dask_address: str | None = None
    ray_address: str | None = None
    n_workers: int | None = Field(default=None, ge=1)
    threads_per_worker: int | None = Field(default=None, ge=1)
    extras: dict[str, Any] = Field(default_factory=dict)


class PartitionSpec(BaseModel):
    """Partition strategy for the run."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["none", "daily", "weekly", "monthly", "symbol", "static"] = "none"
    key: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    values: list[str] = Field(default_factory=list)


class FetchSliceSpec(BaseModel):
    """Cross-provider fetch slicing controls used by APIs and UI builders."""

    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(default_factory=list)
    symbol_mode: Literal["explicit", "all_active", "query", "universe"] = "explicit"
    query: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    interval: str | None = None
    timeframe: str | None = None
    limit: int | None = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0)
    cursor: str | None = None
    partition: PartitionSpec = Field(default_factory=PartitionSpec)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    def to_source_kwargs(self) -> dict[str, Any]:
        """Drop empty values and return kwargs suitable for a source node."""

        payload = self.model_dump(exclude_none=True)
        if not self.symbols:
            payload.pop("symbols", None)
        if not self.provider_options:
            payload.pop("provider_options", None)
        if self.partition.kind == "none":
            payload.pop("partition", None)
        return payload


class SchedulingSpec(BaseModel):
    """Optional scheduling metadata read by Dagster sensors."""

    model_config = ConfigDict(extra="forbid")

    cron: str | None = None
    timezone: str = "UTC"
    enabled: bool = False


class PipelineManifest(BaseModel):
    """Top-level manifest for a single pipeline.

    Field shape:

    - ``id`` — optional opaque id (assigned by the persistence layer).
    - ``name`` — short slug; combined with ``namespace`` it forms the
      Dagster asset key.
    - ``namespace`` — Iceberg namespace / Dagster asset group.
    - ``source`` — exactly one :class:`NodeSpec` of kind ``source``.
    - ``transforms`` — zero or more transform NodeSpecs (executed in
      order).
    - ``sink`` — exactly one :class:`NodeSpec` of kind ``sink``.
    - ``compute`` — backend selection.
    - ``partitions`` — partition strategy.
    - ``schedule`` — cron-style scheduling.
    - ``tags`` — free-form tags (UI / DataHub).
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, description="Persistence id")
    name: str = Field(..., min_length=1, max_length=160)
    namespace: str = Field(default="aqp")
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    source: NodeSpec
    transforms: list[NodeSpec] = Field(default_factory=list)
    sink: NodeSpec

    compute: ComputeSpec = Field(default_factory=ComputeSpec)
    partitions: PartitionSpec = Field(default_factory=PartitionSpec)
    schedule: SchedulingSpec = Field(default_factory=SchedulingSpec)

    owner: str | None = None
    version: int = 1
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("namespace")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = (v or "aqp").strip()
        if not v:
            return "aqp"
        return v

    @property
    def asset_key(self) -> tuple[str, str]:
        """Dagster asset key prefix used by the code-location."""
        return (self.namespace, self.name)

    def iter_node_specs(self) -> list[NodeSpec]:
        """Source -> transforms... -> sink, in execution order."""
        return [self.source, *self.transforms, self.sink]

    def to_summary(self) -> dict[str, Any]:
        """Tiny summary dict used by /engine list endpoints."""
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "source": self.source.name,
            "transforms": [t.name for t in self.transforms],
            "sink": self.sink.name,
            "compute_backend": self.compute.backend.value,
            "tags": list(self.tags),
            "enabled": self.enabled,
            "version": self.version,
        }


__all__ = [
    "ComputeBackendKind",
    "ComputeSpec",
    "FetchSliceSpec",
    "NodeSpec",
    "PartitionSpec",
    "PipelineManifest",
    "SchedulingSpec",
]
