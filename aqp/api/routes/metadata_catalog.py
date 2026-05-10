"""Unified metadata catalog endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

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
    medallion_layer: str | None = None
    business_metadata: dict[str, Any] = Field(default_factory=dict)
    data_contract: dict[str, Any] = Field(default_factory=dict)
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


class MetadataDatasetPatchRequest(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    load_mode: str | None = None
    medallion_layer: str | None = None
    business_metadata: dict[str, Any] | None = None
    data_contract: dict[str, Any] | None = None


class MetadataDatasetCreateRequest(BaseModel):
    name: str
    provider: str = "self_service"
    domain: str = "user.dataset"
    namespace: str | None = None
    table: str | None = None
    iceberg_identifier: str | None = None
    storage_uri: str | None = None
    source_uri: str | None = None
    frequency: str | None = None
    load_mode: str = "registered"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    medallion_layer: str | None = None
    business_metadata: dict[str, Any] = Field(default_factory=dict)
    data_contract: dict[str, Any] = Field(default_factory=dict)


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


@router.post("/datasets", response_model=MetadataDatasetResponse)
def create_metadata_dataset(payload: MetadataDatasetCreateRequest) -> dict[str, Any]:
    from datetime import datetime

    from aqp.persistence.db import get_session
    from aqp.persistence.models import DatasetCatalog

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    iceberg_identifier = payload.iceberg_identifier
    if not iceberg_identifier and payload.namespace and payload.table:
        iceberg_identifier = f"{payload.namespace.strip()}.{payload.table.strip()}"
    with get_session() as session:
        existing = None
        if iceberg_identifier:
            existing = session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.iceberg_identifier == iceberg_identifier)
                .limit(1)
            ).scalar_one_or_none()
        if existing is None:
            existing = session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.provider == payload.provider)
                .where(DatasetCatalog.name == name)
                .limit(1)
            ).scalar_one_or_none()
        if existing is None:
            row = DatasetCatalog(
                name=name,
                provider=payload.provider,
                domain=payload.domain,
                frequency=payload.frequency,
                storage_uri=payload.storage_uri,
                description=payload.description,
                tags=list(payload.tags or []),
                iceberg_identifier=iceberg_identifier,
                load_mode=payload.load_mode,
                source_uri=payload.source_uri,
                medallion_layer=payload.medallion_layer,
                business_metadata=dict(payload.business_metadata or {}),
                data_contract_json=dict(payload.data_contract or {}),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
        else:
            row = existing
            row.description = payload.description if payload.description is not None else row.description
            row.tags = list(payload.tags or row.tags or [])
            row.iceberg_identifier = iceberg_identifier or row.iceberg_identifier
            row.source_uri = payload.source_uri or row.source_uri
            row.load_mode = payload.load_mode or row.load_mode
            row.medallion_layer = payload.medallion_layer or row.medallion_layer
            if payload.business_metadata:
                row.business_metadata = dict(payload.business_metadata)
            if payload.data_contract:
                row.data_contract_json = dict(payload.data_contract)
            row.updated_at = datetime.utcnow()
            session.add(row)
        session.commit()
        session.refresh(row)
        result = _service.get_dataset(row.id) or {}
        try:
            from aqp.cache import cache_write_through

            cache_write_through("datasets", result)
        except Exception:  # noqa: BLE001
            pass
        return result


@router.patch("/datasets/{dataset_id}", response_model=MetadataDatasetResponse)
def patch_metadata_dataset(dataset_id: str, payload: MetadataDatasetPatchRequest) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="No metadata fields provided.")
    try:
        dataset = _service.patch_dataset(dataset_id, **values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if dataset is None:
        raise HTTPException(404, f"dataset {dataset_id!r} not found")
    return dataset


@router.get("/datasets/{dataset_id}/lineage", response_model=MetadataLineageResponse)
def dataset_lineage(dataset_id: str, limit: int = Query(default=250, ge=1, le=2000)) -> dict[str, Any]:
    return _service.lineage(dataset_id, limit=limit)


@router.get("/health")
def metadata_catalog_health() -> dict[str, Any]:
    return _service.health()
