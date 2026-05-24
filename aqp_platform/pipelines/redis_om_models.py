"""Redis OM models for documents, chunks, annotations, artifacts, and cache entries.

Models are exposed even when redis-om is not installed by providing
stub classes so ``from pipelines.redis_om_models import DocumentRecord``
always succeeds.  Use :func:`ensure_migrated` to create/refresh the
underlying RediSearch indexes.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from .config import get_redis_settings

logger = logging.getLogger(__name__)


_OM_AVAILABLE = True
try:  # pragma: no cover - optional dependency
    from redis_om import Field, JsonModel, HashModel, Migrator, get_redis_connection
except Exception as exc:  # pragma: no cover
    _OM_AVAILABLE = False
    Field = None  # type: ignore
    JsonModel = None  # type: ignore
    HashModel = None  # type: ignore
    Migrator = None  # type: ignore
    get_redis_connection = None  # type: ignore
    logger.info("redis-om not installed; model classes will be stubs (%s)", exc)


# ---------------------------------------------------------------------------
# Connection bootstrap - redis-om reads REDIS_OM_URL, fall back to REDIS_URL.
# ---------------------------------------------------------------------------
def _bootstrap_om_url() -> None:
    if os.environ.get("REDIS_OM_URL"):
        return
    settings = get_redis_settings()
    os.environ["REDIS_OM_URL"] = settings.url or settings.dsn()


_bootstrap_om_url()


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------
if _OM_AVAILABLE:

    class DocumentRecord(JsonModel):  # type: ignore[misc]
        """Top-level document metadata in the global document store."""

        pk: str = Field(index=True, primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        title: str = Field(index=True, full_text_search=True)
        collection: str = Field(index=True, default="default")
        source: str = Field(index=True, default="upload")
        source_uri: str = Field(default="")
        mime_type: str = Field(default="application/octet-stream")
        tags: list[str] = Field(index=True, default_factory=list)
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        size_bytes: int = Field(index=True, sortable=True, default=0)
        chunk_count: int = Field(index=True, sortable=True, default=0)
        checksum: str = Field(index=True, default="")
        description: str = Field(default="", full_text_search=True)
        owner: str = Field(index=True, default="system")

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "doc"

    class DocumentChunk(JsonModel):  # type: ignore[misc]
        """RAG chunk linked to a DocumentRecord.  Carries only metadata;
        the actual chunk text + embedding live under `chunk:{index}:{id}`
        keys managed by `pipelines.redis_vectors` so that RediSearch
        indexes them with a single FT.CREATE."""

        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        doc_pk: str = Field(index=True)
        chunk_index: int = Field(index=True, sortable=True)
        collection: str = Field(index=True, default="default")
        checksum: str = Field(index=True, default="")
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "chunk_meta"

    class Annotation(JsonModel):  # type: ignore[misc]
        """Freehand annotation written by a user against a document."""

        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        doc_pk: str = Field(index=True)
        author: str = Field(index=True, default="anonymous")
        body: str = Field(full_text_search=True, default="")
        tags: list[str] = Field(index=True, default_factory=list)
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)
        updated_at: float = Field(index=True, sortable=True, default_factory=time.time)
        anchor: str = Field(default="")  # e.g. "chunk:5" or "page:3"

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "ann"

    class Artifact(JsonModel):  # type: ignore[misc]
        """Ingestion receipt for a MinIO JSON artifact."""

        pk: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
        bucket: str = Field(index=True)
        object_key: str = Field(index=True, full_text_search=True)
        sha256: str = Field(index=True)
        size_bytes: int = Field(index=True, sortable=True, default=0)
        ingested_at: float = Field(index=True, sortable=True, default_factory=time.time)
        doc_pk: str = Field(index=True, default="")  # document created from this artifact
        tags: list[str] = Field(index=True, default_factory=list)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "artifact"

    class CacheEntry(HashModel):  # type: ignore[misc]
        """Lightweight hash-backed metadata for cache keys.

        The cache values themselves remain plain strings under
        `cache:{module}:{sha}` for easy ``MGET`` access; this model
        stores auxiliary info such as last-hit time and origin URL.
        """

        pk: str = Field(primary_key=True)
        namespace: str = Field(index=True)
        key_sha: str = Field(index=True)
        created_at: float = Field(index=True, sortable=True, default_factory=time.time)
        last_hit_at: float = Field(sortable=True, default=0.0)
        hit_count: int = Field(sortable=True, default=0)
        ttl_seconds: int = Field(default=0)

        class Meta:
            global_key_prefix = "rpi"
            model_key_prefix = "cache_meta"

    def ensure_migrated() -> None:
        """Create or update every RediSearch index backing the models."""
        try:
            Migrator().run()
        except Exception as exc:  # pragma: no cover
            logger.warning("redis-om migration failed: %s", exc)

    _OM_MODELS = [DocumentRecord, DocumentChunk, Annotation, Artifact, CacheEntry]

else:  # pragma: no cover - stubs when redis-om not installed

    class _OMStub:
        _NOT_INSTALLED_MSG = (
            "redis-om is not installed. `pip install redis-om` to use "
            "DocumentRecord/DocumentChunk/Annotation/Artifact/CacheEntry."
        )

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(self._NOT_INSTALLED_MSG)

        @classmethod
        def find(cls, *_, **__) -> Any:  # noqa: ANN401
            raise RuntimeError(cls._NOT_INSTALLED_MSG)

        @classmethod
        def get(cls, *_, **__) -> Any:
            raise RuntimeError(cls._NOT_INSTALLED_MSG)

    class DocumentRecord(_OMStub): ...  # type: ignore[misc,valid-type]

    class DocumentChunk(_OMStub): ...  # type: ignore[misc,valid-type]

    class Annotation(_OMStub): ...  # type: ignore[misc,valid-type]

    class Artifact(_OMStub): ...  # type: ignore[misc,valid-type]

    class CacheEntry(_OMStub): ...  # type: ignore[misc,valid-type]

    def ensure_migrated() -> None:
        logger.info("redis-om not installed; ensure_migrated is a no-op")

    _OM_MODELS = []


__all__ = [
    "Annotation",
    "Artifact",
    "CacheEntry",
    "DocumentChunk",
    "DocumentRecord",
    "ensure_migrated",
]
