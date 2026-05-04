"""Unified entity registry API.

Sibling of :mod:`aqp.api.routes.entities` (which serves the structured
entity-graph: Issuer, KeyExecutive, ...). The unified registry lives
at ``/registry/entities`` and is backed by
:mod:`aqp.persistence.models_entity_registry`.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aqp.data.entities import registry as entity_registry
from aqp.data.entities.sync import active_instruments, sync_active_instruments_to_graph
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/registry/entities", tags=["entity-registry"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EntitySummary(BaseModel):
    id: str
    kind: str
    canonical_name: str
    short_name: str | None = None
    primary_identifier: str | None = None
    primary_identifier_scheme: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float | None = None
    source_dataset: str | None = None
    source_extractor: str | None = None
    is_canonical: bool = True
    instrument_id: str | None = None
    issuer_id: str | None = None
    parent_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntityDetail(EntitySummary):
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class EntityCreate(BaseModel):
    kind: str
    canonical_name: str
    primary_identifier: str | None = None
    primary_identifier_scheme: str | None = None
    short_name: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    confidence: float | None = None
    source_dataset: str | None = None
    source_extractor: str | None = None
    instrument_id: str | None = None
    issuer_id: str | None = None
    parent_id: str | None = None


class IdentifierLink(BaseModel):
    scheme: str
    value: str
    source: str | None = None
    confidence: float | None = None


class RelationCreate(BaseModel):
    object_id: str
    predicate: str
    confidence: float | None = None
    provenance: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class AnnotationCreate(BaseModel):
    content: str
    kind: str = "description"
    author: str | None = "user"
    citations: list[str] = Field(default_factory=list)
    confidence: float | None = None
    model: str | None = None
    provider: str | None = None


class ExtractRequest(BaseModel):
    flavor: str
    iceberg_identifier: str | None = None
    head_rows: int | None = 200_000
    extractor_kwargs: dict[str, Any] = Field(default_factory=dict)


class EnrichRequest(BaseModel):
    enricher: str = "description"
    entity_ids: list[str]
    enricher_kwargs: dict[str, Any] = Field(default_factory=dict)


class InstrumentLoadRequest(BaseModel):
    vt_symbols: list[str] = Field(default_factory=list)
    provider: str = "auto"
    start: str | None = None
    end: str | None = None
    interval: str | None = None
    dataset_template: str = "market_bars_by_instrument"
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[EntitySummary])
def list_entities(
    kind: str | None = Query(default=None),
    source_dataset: str | None = Query(default=None),
    canonical_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return entity_registry.list_entities(
        kind=kind,
        source_dataset=source_dataset,
        canonical_only=canonical_only,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=list[EntitySummary])
def search_entities(
    q: str = Query(..., min_length=2),
    kind: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, Any]]:
    return entity_registry.search_entities(q, kind=kind, limit=limit)


@router.get("/graph/explorer")
def graph_explorer(
    root_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    depth: int = Query(default=2, ge=1, le=4),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    """Return normalized graph nodes/edges for the canonical entity graph explorer."""
    return entity_registry.entity_graph(root_id=root_id, query=q, depth=depth, limit=limit)


@router.get("/instruments/active")
def list_active_instruments(
    refresh: bool = Query(default=False),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> dict[str, Any]:
    """Return the cached active instrument universe used by graph and load flows."""
    with get_session() as session:
        rows = active_instruments(session=session, refresh=refresh, limit=limit)
    return {"count": len(rows), "instruments": rows}


@router.post("/instruments/sync")
def sync_instrument_graph(limit: int = Query(default=5000, ge=1, le=20000)) -> dict[str, Any]:
    """Seed active instruments into the configured entity graph store."""
    with get_session() as session:
        return sync_active_instruments_to_graph(session=session, limit=limit)


@router.post("/instruments/load-template")
def instrument_load_template(payload: InstrumentLoadRequest) -> dict[str, Any]:
    """Return a reusable manifest-style template for instrument-level data loading."""
    symbols = [str(v).strip().upper() for v in payload.vt_symbols if str(v).strip()]
    return {
        "template": payload.dataset_template,
        "provider": payload.provider,
        "dry_run": payload.dry_run,
        "manifest": {
            "kind": "instrument_data_load",
            "dataset_template": payload.dataset_template,
            "symbols": symbols,
            "params": {
                "start": payload.start,
                "end": payload.end,
                "interval": payload.interval,
                "provider": payload.provider,
            },
            "entity_edges": [
                {"entity_kind": "security", "identifier_scheme": "vt_symbol", "identifier": symbol}
                for symbol in symbols
            ],
        },
    }


@router.post("", response_model=EntitySummary)
def create_entity(payload: EntityCreate) -> dict[str, Any]:
    result = entity_registry.upsert_entity(**payload.model_dump())
    if result is None:
        raise HTTPException(status_code=503, detail="entity registry unavailable")
    return result


@router.get("/{entity_id}", response_model=EntityDetail)
def get_entity(entity_id: str) -> dict[str, Any]:
    row = entity_registry.get_entity(entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return row


@router.get("/{entity_id}/neighbors")
def get_entity_neighbors(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=64, ge=1, le=200),
) -> dict[str, Any]:
    return entity_registry.neighbors(entity_id, depth=depth, limit=limit)


@router.get("/{entity_id}/datasets")
def get_entity_datasets(entity_id: str) -> dict[str, Any]:
    """Return dataset linkage rows for ``entity_id``."""
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_entity_registry import EntityDatasetLink

        with get_session() as session:
            rows = (
                session.execute(
                    select(EntityDatasetLink)
                    .where(EntityDatasetLink.entity_id == entity_id)
                    .order_by(EntityDatasetLink.created_at.desc())
                    .limit(200)
                )
                .scalars()
                .all()
            )
            return {
                "entity_id": entity_id,
                "datasets": [
                    {
                        "id": r.id,
                        "dataset_catalog_id": r.dataset_catalog_id,
                        "dataset_version_id": r.dataset_version_id,
                        "iceberg_identifier": r.iceberg_identifier,
                        "row_count": r.row_count,
                        "role": r.role,
                        "coverage_start": (
                            r.coverage_start.isoformat() if r.coverage_start else None
                        ),
                        "coverage_end": (
                            r.coverage_end.isoformat() if r.coverage_end else None
                        ),
                    }
                    for r in rows
                ],
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_entity_datasets failed: %s", exc)
        return {"entity_id": entity_id, "datasets": [], "error": str(exc)}


@router.post("/{entity_id}/identifiers")
def add_identifier(entity_id: str, payload: IdentifierLink) -> dict[str, Any]:
    result = entity_registry.link_entity_identifier(
        entity_id=entity_id,
        **payload.model_dump(),
    )
    if result is None:
        raise HTTPException(status_code=503, detail="identifier link failed")
    return result


@router.post("/{entity_id}/relations")
def add_relation(entity_id: str, payload: RelationCreate) -> dict[str, Any]:
    result = entity_registry.add_entity_relation(
        subject_id=entity_id,
        **payload.model_dump(),
    )
    if result is None:
        raise HTTPException(status_code=503, detail="relation create failed")
    return result


@router.post("/{entity_id}/annotations")
def add_annotation(entity_id: str, payload: AnnotationCreate) -> dict[str, Any]:
    result = entity_registry.add_annotation(
        entity_id=entity_id,
        **payload.model_dump(),
    )
    if result is None:
        raise HTTPException(status_code=503, detail="annotation create failed")
    return result


@router.post("/extract")
def trigger_extraction(payload: ExtractRequest) -> dict[str, Any]:
    """Run an extractor synchronously (small) or queue via Celery (large)."""
    from aqp.tasks.entity_tasks import extract_entities

    async_result = extract_entities.delay(
        flavor=payload.flavor,
        iceberg_identifier=payload.iceberg_identifier,
        head_rows=payload.head_rows,
        extractor_kwargs=payload.extractor_kwargs,
    )
    return {"task_id": async_result.id, "status": "queued"}


@router.post("/enrich")
def trigger_enrichment(payload: EnrichRequest) -> dict[str, Any]:
    """Queue one Celery task per entity for the requested enricher."""
    from aqp.tasks.entity_tasks import enrich_entity

    task_ids: list[str] = []
    for entity_id in payload.entity_ids:
        result = enrich_entity.delay(
            entity_id=entity_id,
            enricher=payload.enricher,
            enricher_kwargs=payload.enricher_kwargs,
        )
        task_ids.append(result.id)
    return {"task_ids": task_ids, "status": "queued", "count": len(task_ids)}


@router.get("/_meta/extractors")
def list_extractor_kinds() -> dict[str, Any]:
    from aqp.data.entities.extractors import EXTRACTOR_REGISTRY

    return {
        "extractors": [
            {"name": name, "class_name": cls.__name__}
            for name, cls in sorted(EXTRACTOR_REGISTRY.items())
        ]
    }


@router.get("/_meta/enrichers")
def list_enricher_kinds() -> dict[str, Any]:
    from aqp.data.entities.enrichers import ENRICHER_REGISTRY

    return {
        "enrichers": [
            {"name": name, "class_name": cls.__name__}
            for name, cls in sorted(ENRICHER_REGISTRY.items())
        ]
    }
