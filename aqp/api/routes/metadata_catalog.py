"""Unified metadata catalog endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from aqp.services.metadata_catalog_service import MetadataCatalogService

router = APIRouter(prefix="/metadata/catalog", tags=["metadata-catalog"])


class MetadataDatasetResponse(BaseModel):
    id: str
    name: str
    provider: str
    domain: str
    namespace: str | None = None
    table: str | None = None
    iceberg_identifier: str | None = None
    storage_uri: str | None = None
    source_uri: str | None = None
    frequency: str | None = None
    load_mode: str = "registered"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    latest_version: int | None = None
    latest_dataset_hash: str | None = None
    latest_row_count: int | None = None
    latest_symbol_count: int | None = None
    latest_file_count: int | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    entity_link_count: int = 0
    data_link_count: int = 0
    streaming_link_count: int = 0
    has_annotation: bool = False
    updated_at: datetime | None = None
    created_at: datetime | None = None
    entry_kind: Literal["dataset", "instrument"] = "dataset"
    vt_symbol: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    asset_class: str | None = None
    security_type: str | None = None
    sector: str | None = None
    industry: str | None = None


class MetadataLineageResponse(BaseModel):
    dataset: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


_service = MetadataCatalogService()


@router.get("/datasets", response_model=list[MetadataDatasetResponse])
def list_metadata_datasets(
    response: Response,
    q: str | None = Query(default=None, description="Search dataset name, provider, domain, or Iceberg identifier."),
    provider: str | None = None,
    domain: str | None = None,
    namespace: str | None = Query(
        default=None,
        description="Iceberg namespace, __registered__, or __universe__ (stock universe / instruments).",
    ),
    include_iceberg_only: bool = True,
    limit: int = Query(default=250, ge=1, le=2000),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return _service.list_datasets(
        query=q,
        provider=provider,
        domain=domain,
        namespace=namespace,
        include_iceberg_only=include_iceberg_only,
        limit=limit,
    )


@router.get("/datasets/{dataset_id}", response_model=MetadataDatasetResponse)
def get_metadata_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = _service.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(404, f"dataset {dataset_id!r} not found")
    return dataset


@router.get("/datasets/{dataset_id}/lineage", response_model=MetadataLineageResponse)
def dataset_lineage(dataset_id: str, limit: int = Query(default=250, ge=1, le=2000)) -> dict[str, Any]:
    return _service.lineage(dataset_id, limit=limit)


@router.get("/health")
def metadata_catalog_health() -> dict[str, Any]:
    return _service.health()
