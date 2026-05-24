"""Document store service.

Orchestrates the end-to-end self-service document pipeline:

    upload -> persist blob to MinIO -> extract text -> chunk -> embed
           -> upsert metadata + chunks into Redis (JSON + RediSearch vector)
           -> surface through the management API and portal UI

Keeps Redis as the primary index (fast full-text + vector search) while
using MinIO as the durable blob store.  JSON artifacts already living in
MinIO can be loaded via :meth:`ingest_minio_artifact` which skips the
upload step and reuses the same chunk + index flow.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from fastapi import UploadFile
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from ..config import Settings
from .redis_service import RedisService

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer("rpi.management.documents")

try:  # lazy optional dependency
    import boto3
    from botocore.config import Config as BotoConfig
except Exception:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    BotoConfig = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DocumentSummary:
    id: str
    title: str
    collection: str
    tags: list[str]
    source: str
    source_uri: str
    mime_type: str
    size_bytes: int
    chunk_count: int
    created_at: float
    updated_at: float
    owner: str
    description: str
    checksum: str


@dataclass(slots=True)
class DocumentSearchHit:
    id: str
    title: str
    text: str
    score: float
    collection: str
    tags: list[str] = field(default_factory=list)
    doc_id: str = ""


@dataclass(slots=True)
class Annotation:
    id: str
    doc_id: str
    author: str
    body: str
    tags: list[str]
    anchor: str
    created_at: float
    updated_at: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _to_float32_bytes(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _deterministic_embedding(text: str, dim: int = 16) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(dim)]


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("chunk size must be > 0")
    if overlap < 0 or overlap >= size:
        overlap = max(0, size // 10)
    step = max(size - overlap, 1)
    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        chunk = text[cursor : cursor + size].strip()
        if chunk:
            chunks.append(chunk)
        cursor += step
    return chunks


def _best_effort_text(content: bytes, mime: str) -> str:
    """Extract a best-effort text rendition from a binary payload.

    Keeps dependencies optional; PDF + structured JSON have dedicated
    parsers, everything else falls back to UTF-8 decoding.
    """
    lower = (mime or "").lower()
    if lower == "application/json":
        try:
            return json.dumps(json.loads(content.decode("utf-8")), indent=2)
        except Exception:
            pass
    if lower == "application/pdf":
        try:
            import pypdf  # type: ignore

            reader = pypdf.PdfReader(io.BytesIO(content))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            try:
                import fitz  # type: ignore (pymupdf)

                with fitz.open(stream=content, filetype="pdf") as doc:
                    return "\n\n".join(page.get_text() for page in doc)
            except Exception as exc:  # pragma: no cover
                logger.debug("PDF parse failed: %s", exc)
                return ""
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _flatten_json(obj: Any, prefix: str = "") -> list[str]:
    """Flatten a JSON object into "path: value" lines for chunking."""
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(value, path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            path = f"{prefix}[{idx}]"
            lines.extend(_flatten_json(value, path))
    else:
        lines.append(f"{prefix}: {obj}")
    return lines


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class DocumentService:
    """High-level service backing the /api/documents endpoints."""

    def __init__(self, settings: Settings, redis: RedisService) -> None:
        self.settings = settings
        self.redis = redis
        self._s3: Any | None = None

    # ------------------------------------------------------------------ #
    # MinIO client
    # ------------------------------------------------------------------ #
    def _get_s3(self) -> Any:
        if self._s3 is None:
            if boto3 is None:
                raise RuntimeError(
                    "boto3 is required for the document store. "
                    "Install the management backend's pyproject.toml deps."
                )
            endpoint = self.settings.minio.endpoint.rstrip("/")
            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id="minioadmin",
                aws_secret_access_key="minioadmin123",
                config=BotoConfig(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return self._s3

    async def _ensure_bucket(self, bucket: str) -> None:
        s3 = self._get_s3()
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            try:
                s3.create_bucket(Bucket=bucket)
            except Exception as exc:  # pragma: no cover
                logger.debug("ensure_bucket %s: %s", bucket, exc)

    # ------------------------------------------------------------------ #
    # Setup - create RediSearch indexes the first time the service runs
    # ------------------------------------------------------------------ #
    async def ensure_indexes(self) -> None:
        """Create the RediSearch indexes backing the document store.

        Silently ignores "index already exists" errors so the endpoint
        is safe to call from readiness probes.
        """
        client = await self.redis._get_client()  # noqa: SLF001

        await self._ensure_chunk_index(client)
        await self._ensure_document_index(client)
        await self._ensure_annotation_index(client)

    async def _ensure_chunk_index(self, client: Any) -> None:
        idx = self.settings.docstore.vector_index_name
        try:
            await client.execute_command("FT.INFO", idx)
            return
        except Exception:
            pass
        dim = self.settings.docstore.embedding_dim
        args: list[Any] = [
            "FT.CREATE", idx,
            "ON", "JSON",
            "PREFIX", 1, "chunk:",
            "SCHEMA",
            "$.text", "AS", "text", "TEXT", "WEIGHT", 1.0,
            "$.metadata.doc_id", "AS", "doc_id", "TAG", "SEPARATOR", "|",
            "$.metadata.collection", "AS", "collection", "TAG", "SEPARATOR", "|",
            "$.metadata.source", "AS", "source", "TAG",
            "$.metadata.tags", "AS", "tags", "TAG", "SEPARATOR", ",",
            "$.metadata.chunk_index", "AS", "chunk_index", "NUMERIC", "SORTABLE",
            "$.metadata.created_at", "AS", "created_at", "NUMERIC", "SORTABLE",
            "$.embedding", "AS", "embedding",
            "VECTOR", "HNSW", 12,
            "TYPE", "FLOAT32",
            "DIM", int(dim),
            "DISTANCE_METRIC", "COSINE",
            "M", 16,
            "EF_CONSTRUCTION", 200,
            "EF_RUNTIME", 40,
        ]
        with _tracer.start_as_current_span("docstore.ft.create_chunks", kind=SpanKind.CLIENT):
            await client.execute_command(*args)
        logger.info("Created chunk index %s (dim=%d)", idx, dim)

    async def _ensure_document_index(self, client: Any) -> None:
        idx = self.settings.docstore.document_index_name
        try:
            await client.execute_command("FT.INFO", idx)
            return
        except Exception:
            pass
        args: list[Any] = [
            "FT.CREATE", idx,
            "ON", "JSON",
            "PREFIX", 1, "doc:",
            "SCHEMA",
            "$.title", "AS", "title", "TEXT", "WEIGHT", 2.0, "SORTABLE",
            "$.description", "AS", "description", "TEXT",
            "$.collection", "AS", "collection", "TAG", "SEPARATOR", "|",
            "$.source", "AS", "source", "TAG",
            "$.tags", "AS", "tags", "TAG", "SEPARATOR", ",",
            "$.owner", "AS", "owner", "TAG",
            "$.mime_type", "AS", "mime_type", "TAG",
            "$.size_bytes", "AS", "size_bytes", "NUMERIC", "SORTABLE",
            "$.chunk_count", "AS", "chunk_count", "NUMERIC", "SORTABLE",
            "$.created_at", "AS", "created_at", "NUMERIC", "SORTABLE",
            "$.updated_at", "AS", "updated_at", "NUMERIC", "SORTABLE",
        ]
        with _tracer.start_as_current_span("docstore.ft.create_docs", kind=SpanKind.CLIENT):
            await client.execute_command(*args)
        logger.info("Created document index %s", idx)

    async def _ensure_annotation_index(self, client: Any) -> None:
        idx = self.settings.docstore.annotation_index_name
        try:
            await client.execute_command("FT.INFO", idx)
            return
        except Exception:
            pass
        args: list[Any] = [
            "FT.CREATE", idx,
            "ON", "JSON",
            "PREFIX", 1, "ann:",
            "SCHEMA",
            "$.body", "AS", "body", "TEXT",
            "$.doc_id", "AS", "doc_id", "TAG", "SEPARATOR", "|",
            "$.author", "AS", "author", "TAG",
            "$.tags", "AS", "tags", "TAG", "SEPARATOR", ",",
            "$.anchor", "AS", "anchor", "TAG",
            "$.created_at", "AS", "created_at", "NUMERIC", "SORTABLE",
            "$.updated_at", "AS", "updated_at", "NUMERIC", "SORTABLE",
        ]
        with _tracer.start_as_current_span("docstore.ft.create_ann", kind=SpanKind.CLIENT):
            await client.execute_command(*args)
        logger.info("Created annotation index %s", idx)

    # ------------------------------------------------------------------ #
    # Upload + ingest
    # ------------------------------------------------------------------ #
    async def upload(
        self,
        file: UploadFile,
        *,
        title: str | None = None,
        tags: Iterable[str] = (),
        collection: str | None = None,
        owner: str = "system",
        description: str = "",
        source: str = "upload",
    ) -> DocumentSummary:
        data = await file.read()
        size = len(data)
        max_bytes = self.settings.docstore.max_upload_mb * 1024 * 1024
        if size > max_bytes:
            raise ValueError(
                f"File too large: {size} bytes exceeds configured "
                f"max ({self.settings.docstore.max_upload_mb} MB)."
            )

        mime = (file.content_type or "").lower() or "application/octet-stream"
        allowed = {m.lower() for m in self.settings.docstore.allowed_mime_types}
        if allowed and mime not in allowed and "application/octet-stream" not in allowed:
            raise ValueError(
                f"Unsupported MIME type {mime}. Allowed: {sorted(allowed)}."
            )

        filename = file.filename or "document.bin"
        checksum = _sha256(data)

        bucket = self.settings.docstore.bucket
        prefix = self.settings.docstore.bucket_prefix
        doc_id = str(uuid.uuid4())
        object_key = f"{prefix.rstrip('/')}/{doc_id}/{filename}"

        await self._ensure_bucket(bucket)
        with _tracer.start_as_current_span("docstore.s3.put_object", kind=SpanKind.CLIENT) as span:
            span.set_attribute("s3.bucket", bucket)
            span.set_attribute("s3.key", object_key)
            self._get_s3().put_object(Bucket=bucket, Key=object_key, Body=data, ContentType=mime)
        source_uri = f"s3://{bucket}/{object_key}"

        text = _best_effort_text(data, mime)
        chunk_count = await self._index_document(
            doc_id=doc_id,
            title=title or filename,
            collection=collection or self.settings.docstore.default_collection,
            tags=[t for t in tags if t],
            source=source,
            source_uri=source_uri,
            mime=mime,
            owner=owner,
            description=description,
            size_bytes=size,
            checksum=checksum,
            text=text,
        )

        return DocumentSummary(
            id=doc_id,
            title=title or filename,
            collection=collection or self.settings.docstore.default_collection,
            tags=list(tags),
            source=source,
            source_uri=source_uri,
            mime_type=mime,
            size_bytes=size,
            chunk_count=chunk_count,
            created_at=time.time(),
            updated_at=time.time(),
            owner=owner,
            description=description,
            checksum=checksum,
        )

    async def _index_document(
        self,
        *,
        doc_id: str,
        title: str,
        collection: str,
        tags: list[str],
        source: str,
        source_uri: str,
        mime: str,
        owner: str,
        description: str,
        size_bytes: int,
        checksum: str,
        text: str,
    ) -> int:
        await self.ensure_indexes()
        client = await self.redis._get_client()  # noqa: SLF001

        now = time.time()
        chunks = _chunk_text(
            text or "",
            self.settings.docstore.chunk_size,
            self.settings.docstore.chunk_overlap,
        )
        embeddings = [
            _deterministic_embedding(c, dim=self.settings.docstore.embedding_dim)
            for c in chunks
        ]

        doc_payload = {
            "id": doc_id,
            "title": title,
            "description": description,
            "collection": collection,
            "source": source,
            "source_uri": source_uri,
            "mime_type": mime,
            "owner": owner,
            "tags": tags,
            "size_bytes": size_bytes,
            "chunk_count": len(chunks),
            "checksum": checksum,
            "created_at": now,
            "updated_at": now,
        }

        with _tracer.start_as_current_span("docstore.upsert_document", kind=SpanKind.CLIENT) as span:
            span.set_attribute("doc.id", doc_id)
            span.set_attribute("doc.chunks", len(chunks))
            pipe = client.pipeline(transaction=False)
            pipe.execute_command("JSON.SET", f"doc:{doc_id}", "$", json.dumps(doc_payload))
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{doc_id}:{idx}"
                chunk_payload = {
                    "id": chunk_id,
                    "text": chunk,
                    "embedding": emb,
                    "metadata": {
                        "doc_id": doc_id,
                        "chunk_index": idx,
                        "collection": collection,
                        "source": source,
                        "tags": tags,
                        "created_at": now,
                    },
                }
                pipe.execute_command("JSON.SET", f"chunk:{chunk_id}", "$", json.dumps(chunk_payload))
            await pipe.execute()

        await self.redis._record_counter("stats:ingest", "documents", 1)  # noqa: SLF001
        await self.redis._record_counter("stats:ingest", "chunks", len(chunks))  # noqa: SLF001
        await self.redis._record_timeseries("stats:ingest:count", float(len(chunks)))  # noqa: SLF001
        return len(chunks)

    # ------------------------------------------------------------------ #
    # List / get / delete
    # ------------------------------------------------------------------ #
    async def list_documents(
        self,
        *,
        query: str | None = None,
        collection: str | None = None,
        tags: Iterable[str] = (),
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentSummary]:
        await self.ensure_indexes()
        client = await self.redis._get_client()  # noqa: SLF001

        filter_parts: list[str] = []
        if collection:
            filter_parts.append(f"@collection:{{{_escape_tag(collection)}}}")
        for tag in tags:
            if tag:
                filter_parts.append(f"@tags:{{{_escape_tag(tag)}}}")
        if query:
            filter_parts.append(f"({query})")
        expr = " ".join(filter_parts) or "*"

        with _tracer.start_as_current_span("docstore.ft.search_docs", kind=SpanKind.CLIENT) as span:
            span.set_attribute("docstore.query", expr)
            raw = await client.execute_command(
                "FT.SEARCH",
                self.settings.docstore.document_index_name,
                expr,
                "LIMIT", offset, limit,
                "SORTBY", "created_at", "DESC",
                "DIALECT", 2,
            )
        return [_parse_document_summary(row) for row in _iter_ft_search_rows(raw)]

    async def get_document(self, doc_id: str) -> DocumentSummary | None:
        client = await self.redis._get_client()  # noqa: SLF001
        try:
            with _tracer.start_as_current_span("docstore.json_get", kind=SpanKind.CLIENT) as span:
                span.set_attribute("doc.id", doc_id)
                raw = await client.execute_command("JSON.GET", f"doc:{doc_id}", "$")
        except Exception:
            return None
        if not raw:
            return None
        try:
            decoded = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            payload = json.loads(decoded)
        except Exception:
            return None
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            return None
        return _summary_from_dict(payload)

    async def delete_document(self, doc_id: str) -> int:
        client = await self.redis._get_client()  # noqa: SLF001
        removed = 0
        with _tracer.start_as_current_span("docstore.delete", kind=SpanKind.CLIENT) as span:
            span.set_attribute("doc.id", doc_id)
            removed += int(await client.delete(f"doc:{doc_id}"))
            async for k in client.scan_iter(match=f"chunk:{doc_id}:*", count=512):
                removed += int(await client.delete(k))
            async for k in client.scan_iter(match=f"ann:{doc_id}:*", count=512):
                removed += int(await client.delete(k))
        return removed

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    async def search_chunks(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        top_k: int = 10,
        collection: str | None = None,
        tags: Iterable[str] = (),
    ) -> list[DocumentSearchHit]:
        await self.ensure_indexes()
        client = await self.redis._get_client()  # noqa: SLF001
        idx = self.settings.docstore.vector_index_name

        filter_parts: list[str] = []
        if collection:
            filter_parts.append(f"@collection:{{{_escape_tag(collection)}}}")
        for tag in tags:
            if tag:
                filter_parts.append(f"@tags:{{{_escape_tag(tag)}}}")
        base_filter = " ".join(filter_parts) or "*"

        keyword_results: list[DocumentSearchHit] = []
        vector_results: list[DocumentSearchHit] = []

        if mode in ("keyword", "hybrid"):
            with _tracer.start_as_current_span("docstore.ft.search_keyword", kind=SpanKind.CLIENT):
                raw = await client.execute_command(
                    "FT.SEARCH",
                    idx,
                    f"({base_filter} {query})",
                    "RETURN", 3, "text", "doc_id", "collection",
                    "LIMIT", 0, top_k,
                    "DIALECT", 2,
                )
            keyword_results = [
                DocumentSearchHit(
                    id=hit["__id__"],
                    title=hit.get("doc_id", ""),
                    text=hit.get("text", ""),
                    collection=hit.get("collection", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=rank_score(rank, top_k),
                    tags=[],
                )
                for rank, hit in enumerate(_iter_ft_search_rows(raw))
            ]

        if mode in ("semantic", "hybrid"):
            qvec = _deterministic_embedding(
                query, dim=self.settings.docstore.embedding_dim
            )
            vector_query = f"({base_filter})=>[KNN {top_k} @embedding $BLOB AS vector_score]"
            with _tracer.start_as_current_span("docstore.ft.knn", kind=SpanKind.CLIENT):
                raw = await client.execute_command(
                    "FT.SEARCH",
                    idx,
                    vector_query,
                    "PARAMS", 2, "BLOB", _to_float32_bytes(qvec),
                    "SORTBY", "vector_score",
                    "RETURN", 4, "vector_score", "text", "doc_id", "collection",
                    "LIMIT", 0, top_k,
                    "DIALECT", 2,
                )
            vector_results = [
                DocumentSearchHit(
                    id=hit["__id__"],
                    title=hit.get("doc_id", ""),
                    text=hit.get("text", ""),
                    collection=hit.get("collection", ""),
                    doc_id=hit.get("doc_id", ""),
                    score=1.0 - float(hit.get("vector_score", 0.0) or 0.0),
                    tags=[],
                )
                for hit in _iter_ft_search_rows(raw)
            ]

        if mode == "keyword":
            return keyword_results
        if mode == "semantic":
            return vector_results
        return _reciprocal_rank_fuse(keyword_results, vector_results, top_k)

    # ------------------------------------------------------------------ #
    # Annotations
    # ------------------------------------------------------------------ #
    async def add_annotation(
        self,
        doc_id: str,
        *,
        body: str,
        author: str = "anonymous",
        tags: Iterable[str] = (),
        anchor: str = "",
    ) -> Annotation:
        client = await self.redis._get_client()  # noqa: SLF001
        await self.ensure_indexes()
        ann_id = str(uuid.uuid4())
        now = time.time()
        payload = {
            "id": ann_id,
            "doc_id": doc_id,
            "author": author,
            "body": body,
            "tags": list(tags),
            "anchor": anchor,
            "created_at": now,
            "updated_at": now,
        }
        with _tracer.start_as_current_span("docstore.ann.create", kind=SpanKind.CLIENT) as span:
            span.set_attribute("ann.id", ann_id)
            span.set_attribute("doc.id", doc_id)
            await client.execute_command(
                "JSON.SET", f"ann:{doc_id}:{ann_id}", "$", json.dumps(payload)
            )
        return Annotation(**payload)

    async def list_annotations(self, doc_id: str) -> list[Annotation]:
        client = await self.redis._get_client()  # noqa: SLF001
        annotations: list[Annotation] = []
        async for key in client.scan_iter(match=f"ann:{doc_id}:*", count=256):
            try:
                raw = await client.execute_command("JSON.GET", key, "$")
                if not raw:
                    continue
                decoded = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
                payload = json.loads(decoded)
                if isinstance(payload, list) and payload:
                    payload = payload[0]
                annotations.append(Annotation(**payload))
            except Exception:
                continue
        annotations.sort(key=lambda a: a.created_at, reverse=True)
        return annotations

    async def delete_annotation(self, doc_id: str, ann_id: str) -> int:
        client = await self.redis._get_client()  # noqa: SLF001
        with _tracer.start_as_current_span("docstore.ann.delete", kind=SpanKind.CLIENT):
            return int(await client.delete(f"ann:{doc_id}:{ann_id}"))

    # ------------------------------------------------------------------ #
    # MinIO artifact browser + ingestion
    # ------------------------------------------------------------------ #
    def list_artifact_buckets(self) -> list[str]:
        return list(self.settings.docstore.artifact_buckets)

    def browse_artifacts(
        self,
        bucket: str,
        prefix: str = "",
        *,
        max_keys: int = 200,
    ) -> list[dict[str, Any]]:
        if bucket not in set(self.settings.docstore.artifact_buckets):
            raise ValueError(
                f"Bucket {bucket} is not in the configured artifact bucket list."
            )
        s3 = self._get_s3()
        try:
            resp = s3.list_objects_v2(
                Bucket=bucket, Prefix=prefix, MaxKeys=max_keys,
            )
        except Exception as exc:
            logger.warning("browse_artifacts failed for %s/%s: %s", bucket, prefix, exc)
            return []
        items: list[dict[str, Any]] = []
        for obj in resp.get("Contents", []) or []:
            key = obj["Key"]
            items.append(
                {
                    "bucket": bucket,
                    "key": key,
                    "size": int(obj.get("Size", 0)),
                    "last_modified": obj.get("LastModified").timestamp()
                    if obj.get("LastModified")
                    else None,
                    "is_json": key.lower().endswith(".json"),
                }
            )
        return items

    async def ingest_minio_artifact(
        self,
        bucket: str,
        key: str,
        *,
        title: str | None = None,
        tags: Iterable[str] = (),
        collection: str | None = None,
        owner: str = "system",
    ) -> DocumentSummary:
        if bucket not in set(self.settings.docstore.artifact_buckets):
            raise ValueError(
                f"Bucket {bucket} is not in the configured artifact bucket list."
            )
        s3 = self._get_s3()
        with _tracer.start_as_current_span("docstore.s3.get_object", kind=SpanKind.CLIENT) as span:
            span.set_attribute("s3.bucket", bucket)
            span.set_attribute("s3.key", key)
            obj = s3.get_object(Bucket=bucket, Key=key)
        data: bytes = obj["Body"].read()
        mime = obj.get("ContentType") or ("application/json" if key.endswith(".json") else "application/octet-stream")

        rendered: str
        if mime == "application/json" or key.lower().endswith(".json"):
            try:
                parsed = json.loads(data.decode("utf-8"))
                rendered = "\n".join(_flatten_json(parsed))
            except Exception:
                rendered = data.decode("utf-8", errors="replace")
        else:
            rendered = _best_effort_text(data, mime)

        doc_id = str(uuid.uuid4())
        source_uri = f"s3://{bucket}/{key}"
        await self._index_document(
            doc_id=doc_id,
            title=title or key.rsplit("/", 1)[-1],
            collection=collection or self.settings.docstore.default_collection,
            tags=[*tags, "artifact", bucket],
            source="minio-artifact",
            source_uri=source_uri,
            mime=mime,
            owner=owner,
            description=f"Ingested from {source_uri}",
            size_bytes=len(data),
            checksum=_sha256(data),
            text=rendered,
        )

        artifact_payload = {
            "pk": str(uuid.uuid4()),
            "bucket": bucket,
            "object_key": key,
            "sha256": _sha256(data),
            "size_bytes": len(data),
            "ingested_at": time.time(),
            "doc_pk": doc_id,
            "tags": list(tags),
        }
        client = await self.redis._get_client()  # noqa: SLF001
        try:
            await client.execute_command(
                "JSON.SET",
                f"artifact:{bucket}:{_sha256(data)}",
                "$",
                json.dumps(artifact_payload),
            )
        except Exception:  # pragma: no cover
            pass

        summary = await self.get_document(doc_id)
        if summary is None:
            summary = DocumentSummary(
                id=doc_id,
                title=title or key.rsplit("/", 1)[-1],
                collection=collection or self.settings.docstore.default_collection,
                tags=list(tags),
                source="minio-artifact",
                source_uri=source_uri,
                mime_type=mime,
                size_bytes=len(data),
                chunk_count=0,
                created_at=time.time(),
                updated_at=time.time(),
                owner=owner,
                description=f"Ingested from {source_uri}",
                checksum=_sha256(data),
            )
        return summary


# ---------------------------------------------------------------------------
# Helpers outside the class
# ---------------------------------------------------------------------------
def _escape_tag(value: str) -> str:
    return value.replace("-", "\\-").replace(":", "\\:").replace(" ", "\\ ")


def _iter_ft_search_rows(raw: Any):
    """Yield dicts from a raw FT.SEARCH response."""
    if not raw or not isinstance(raw, list):
        return
    it = iter(raw[1:])
    for key in it:
        fields = next(it, None)
        if fields is None:
            break
        data: dict[str, Any] = {}
        fit = iter(fields)
        for k in fit:
            v = next(fit, None)
            data[_decode(k)] = _decode(v)
        data["__id__"] = _decode(key)
        if "$" in data:
            try:
                payload = json.loads(data["$"])
                if isinstance(payload, list) and payload:
                    payload = payload[0]
                if isinstance(payload, dict):
                    for k, v in payload.items():
                        data.setdefault(k, v)
            except Exception:
                pass
        yield data


def _parse_document_summary(data: dict[str, Any]) -> DocumentSummary:
    return DocumentSummary(
        id=data.get("id") or data.get("__id__", "").split(":", 1)[-1],
        title=str(data.get("title", "")),
        collection=str(data.get("collection", "")),
        tags=list(data.get("tags") or []) if isinstance(data.get("tags"), list) else _split_tags(data.get("tags")),
        source=str(data.get("source", "")),
        source_uri=str(data.get("source_uri", "")),
        mime_type=str(data.get("mime_type", "")),
        size_bytes=int(float(data.get("size_bytes") or 0)),
        chunk_count=int(float(data.get("chunk_count") or 0)),
        created_at=float(data.get("created_at") or 0.0),
        updated_at=float(data.get("updated_at") or 0.0),
        owner=str(data.get("owner", "")),
        description=str(data.get("description", "")),
        checksum=str(data.get("checksum", "")),
    )


def _summary_from_dict(payload: dict[str, Any]) -> DocumentSummary:
    return _parse_document_summary({**payload, "__id__": f"doc:{payload.get('id', '')}"})


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [v for v in value.split(",") if v]
    return []


def _decode(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode()
        except UnicodeDecodeError:
            return value
    return value


def rank_score(rank: int, total: int) -> float:
    """Linear score helper to blend keyword results with vector scores."""
    if total <= 0:
        return 0.0
    return max(0.0, 1.0 - rank / total)


def _reciprocal_rank_fuse(
    a: list[DocumentSearchHit],
    b: list[DocumentSearchHit],
    top_k: int,
    k: int = 60,
) -> list[DocumentSearchHit]:
    scores: dict[str, float] = {}
    items: dict[str, DocumentSearchHit] = {}
    for rank, hit in enumerate(a):
        scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank + 1)
        items.setdefault(hit.id, hit)
    for rank, hit in enumerate(b):
        scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank + 1)
        items.setdefault(hit.id, hit)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    fused: list[DocumentSearchHit] = []
    for key, score in ordered[:top_k]:
        hit = items[key]
        fused.append(
            DocumentSearchHit(
                id=hit.id,
                title=hit.title,
                text=hit.text,
                collection=hit.collection,
                doc_id=hit.doc_id,
                tags=hit.tags,
                score=score,
            )
        )
    return fused


__all__ = [
    "Annotation",
    "DocumentSearchHit",
    "DocumentService",
    "DocumentSummary",
]
