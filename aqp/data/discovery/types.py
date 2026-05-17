"""Shared types for the discovery surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DiscoveryLifecycleState = Literal[
    "ingested",      # has a materialised Iceberg / parquet payload
    "pending",       # rows / connections exist but haven't synced yet
    "orphan",        # Iceberg table with no Postgres row
    "external_only", # SourceLibraryEntry only — no DatasetCatalog row
]
"""Lifecycle classification surfaced in the discovery browser filter chips."""


class DiscoveryEntry(BaseModel):
    """One row in the unified discovery view."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable id; DatasetCatalog.id when available, else a derived sentinel.")
    name: str
    provider: str
    domain: str | None = None
    lifecycle_state: DiscoveryLifecycleState
    dataset_kind: str | None = None
    is_ingested: bool = False
    iceberg_identifier: str | None = None
    namespace: str | None = None
    medallion_layer: str | None = None
    description: str | None = None
    docs_url: str | None = None
    source_uri: str | None = None
    tags: list[str] = Field(default_factory=list)
    spec_hash: str | None = None
    external_spec: dict[str, Any] = Field(default_factory=dict)
    business_metadata: dict[str, Any] = Field(default_factory=dict)
    data_contract: dict[str, Any] = Field(default_factory=dict)
    suggested_connector: str | None = None
    suggested_kind: str | None = None
    airbyte_connection_id: str | None = None
    promote_url: str | None = None
    updated_at: datetime | None = None


class DiscoveryPage(BaseModel):
    """Paged response shape for ``GET /discovery/entries``."""

    items: list[DiscoveryEntry] = Field(default_factory=list)
    total: int = 0
    next_cursor: int | None = None
    by_lifecycle: dict[str, int] = Field(default_factory=dict)


class CreateExternalEntryRequest(BaseModel):
    """Payload for ``POST /discovery/entries``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str = "self_service"
    domain: str = "user.dataset"
    description: str | None = None
    source_uri: str | None = None
    docs_url: str | None = None
    suggested_connector: str | None = None
    suggested_kind: str | None = "external"
    tags: list[str] = Field(default_factory=list)
    business_metadata: dict[str, Any] = Field(default_factory=dict)
    data_contract: dict[str, Any] = Field(default_factory=dict)


class UpdateEntryRequest(BaseModel):
    """Patch payload for ``PATCH /discovery/entries/{id}``."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    docs_url: str | None = None
    source_uri: str | None = None
    suggested_connector: str | None = None
    suggested_kind: str | None = None
    tags: list[str] | None = None
    business_metadata: dict[str, Any] | None = None
    data_contract: dict[str, Any] | None = None


class PromoteRequest(BaseModel):
    """Payload for ``POST /discovery/entries/{id}/promote``."""

    model_config = ConfigDict(extra="forbid")

    target_kind: Literal["airbyte_builder", "fetcher_stub"] = "airbyte_builder"
    notes: str | None = None


class PromoteResponse(BaseModel):
    """Response shape for ``POST /discovery/entries/{id}/promote``."""

    entry_id: str
    target_kind: str
    redirect_url: str
    builder_state: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CreateExternalEntryRequest",
    "DiscoveryEntry",
    "DiscoveryLifecycleState",
    "DiscoveryPage",
    "PromoteRequest",
    "PromoteResponse",
    "UpdateEntryRequest",
]
