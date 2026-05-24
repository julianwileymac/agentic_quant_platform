"""Self-service document store endpoints.

Powers the `/documents` section of the control panel portal:

    - Upload binary/PDF/JSON files
    - List / search / delete documents
    - Annotate documents with freehand notes
    - Browse + ingest existing JSON artifacts from MinIO

Everything is backed by the shared Redis 8 Stack deployment
(JSON + RediSearch vector + TimeSeries + Bloom).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..services import DocumentService, RedisService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Cached dependency injection
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _redis_singleton(settings_id: int) -> RedisService:  # noqa: ARG001 - id for cache key
    return RedisService(get_settings())


@lru_cache(maxsize=1)
def _document_singleton(settings_id: int) -> DocumentService:  # noqa: ARG001
    settings = get_settings()
    return DocumentService(settings, _redis_singleton(id(settings)))


def get_document_service(
    settings: Settings = Depends(get_settings),
) -> DocumentService:
    return _document_singleton(id(settings))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class DocumentSummaryModel(BaseModel):
    id: str
    title: str
    collection: str
    tags: list[str] = Field(default_factory=list)
    source: str
    source_uri: str = ""
    mime_type: str
    size_bytes: int
    chunk_count: int
    created_at: float
    updated_at: float
    owner: str
    description: str = ""
    checksum: str = ""


class DocumentSearchHitModel(BaseModel):
    id: str
    title: str
    text: str
    score: float
    collection: str
    doc_id: str
    tags: list[str] = Field(default_factory=list)


class AnnotationModel(BaseModel):
    id: str
    doc_id: str
    author: str
    body: str
    tags: list[str]
    anchor: str
    created_at: float
    updated_at: float


class AnnotationCreate(BaseModel):
    body: str = Field(min_length=1, max_length=32768)
    author: str = "anonymous"
    tags: list[str] = Field(default_factory=list)
    anchor: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    mode: str = Field(default="hybrid", pattern="^(hybrid|semantic|keyword)$")
    top_k: int = Field(default=10, ge=1, le=100)
    collection: str | None = None
    tags: list[str] = Field(default_factory=list)


class ArtifactListEntry(BaseModel):
    bucket: str
    key: str
    size: int
    last_modified: float | None
    is_json: bool


class ArtifactIngestRequest(BaseModel):
    bucket: str
    key: str
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    collection: str | None = None
    owner: str = "system"


def _summary_to_model(summary: Any) -> DocumentSummaryModel:
    if hasattr(summary, "__dataclass_fields__"):
        return DocumentSummaryModel(**asdict(summary))
    return DocumentSummaryModel(**summary)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=DocumentSummaryModel, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document to upload")],
    title: Annotated[str | None, Form()] = None,
    tags: Annotated[str, Form()] = "",
    collection: Annotated[str | None, Form()] = None,
    owner: Annotated[str, Form()] = "system",
    description: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "upload",
    service: DocumentService = Depends(get_document_service),
) -> DocumentSummaryModel:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        summary = await service.upload(
            file,
            title=title,
            tags=tag_list,
            collection=collection,
            owner=owner,
            description=description,
            source=source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Upload failed; see server logs.") from exc
    return _summary_to_model(summary)


@router.get("", response_model=list[DocumentSummaryModel])
async def list_documents(
    query: str | None = Query(default=None, description="Free-text title/description filter"),
    collection: str | None = Query(default=None),
    tag: list[str] = Query(default_factory=list, description="Tag filter (repeatable)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentSummaryModel]:
    rows = await service.list_documents(
        query=query, collection=collection, tags=tag, limit=limit, offset=offset,
    )
    return [_summary_to_model(r) for r in rows]


@router.get("/{doc_id}", response_model=DocumentSummaryModel)
async def get_document(
    doc_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentSummaryModel:
    summary = await service.get_document(doc_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return _summary_to_model(summary)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict[str, Any]:
    removed = await service.delete_document(doc_id)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return {"deleted": removed, "id": doc_id}


@router.post("/search", response_model=list[DocumentSearchHitModel])
async def search_documents(
    payload: SearchRequest,
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentSearchHitModel]:
    try:
        hits = await service.search_chunks(
            payload.query,
            mode=payload.mode,
            top_k=payload.top_k,
            collection=payload.collection,
            tags=payload.tags,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("search_documents failed: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed.") from exc
    return [DocumentSearchHitModel(**asdict(h)) for h in hits]


# ---------------------------- Annotations ---------------------------- #
@router.post("/{doc_id}/annotations", response_model=AnnotationModel, status_code=201)
async def create_annotation(
    doc_id: str,
    payload: AnnotationCreate,
    service: DocumentService = Depends(get_document_service),
) -> AnnotationModel:
    ann = await service.add_annotation(
        doc_id,
        body=payload.body,
        author=payload.author,
        tags=payload.tags,
        anchor=payload.anchor,
    )
    return AnnotationModel(**asdict(ann))


@router.get("/{doc_id}/annotations", response_model=list[AnnotationModel])
async def list_annotations(
    doc_id: str,
    service: DocumentService = Depends(get_document_service),
) -> list[AnnotationModel]:
    items = await service.list_annotations(doc_id)
    return [AnnotationModel(**asdict(a)) for a in items]


@router.delete("/{doc_id}/annotations/{ann_id}")
async def delete_annotation(
    doc_id: str,
    ann_id: str,
    service: DocumentService = Depends(get_document_service),
) -> dict[str, Any]:
    removed = await service.delete_annotation(doc_id, ann_id)
    if removed == 0:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"deleted": removed, "id": ann_id, "doc_id": doc_id}


# ---------------------------- MinIO artifacts ---------------------------- #
@router.get("/artifacts/buckets", response_model=list[str])
async def list_artifact_buckets(
    service: DocumentService = Depends(get_document_service),
) -> list[str]:
    return service.list_artifact_buckets()


@router.get("/artifacts/browse", response_model=list[ArtifactListEntry])
async def browse_artifacts(
    bucket: str = Query(..., description="MinIO bucket name"),
    prefix: str = Query(default="", description="Object key prefix"),
    max_keys: int = Query(default=200, ge=1, le=1000),
    service: DocumentService = Depends(get_document_service),
) -> list[ArtifactListEntry]:
    try:
        entries = service.browse_artifacts(bucket, prefix=prefix, max_keys=max_keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("browse_artifacts failed: %s", exc)
        raise HTTPException(status_code=500, detail="Artifact listing failed.") from exc
    return [ArtifactListEntry(**entry) for entry in entries]


@router.post("/artifacts/ingest", response_model=DocumentSummaryModel, status_code=201)
async def ingest_artifact(
    payload: ArtifactIngestRequest,
    service: DocumentService = Depends(get_document_service),
) -> DocumentSummaryModel:
    try:
        summary = await service.ingest_minio_artifact(
            payload.bucket,
            payload.key,
            title=payload.title,
            tags=payload.tags,
            collection=payload.collection,
            owner=payload.owner,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_artifact failed: %s", exc)
        raise HTTPException(status_code=500, detail="Artifact ingestion failed.") from exc
    return _summary_to_model(summary)
