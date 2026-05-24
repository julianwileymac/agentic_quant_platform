"""Vectorization and vector-store helpers."""

from __future__ import annotations

import hashlib
from typing import Any


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    chunks: list[str] = []
    cursor = 0
    step = max(chunk_size - overlap, 1)
    while cursor < len(text):
        chunks.append(text[cursor : cursor + chunk_size])
        cursor += step
    return [chunk for chunk in chunks if chunk.strip()]


def deterministic_embedding(text: str, dim: int = 16) -> list[float]:
    """Deterministic fallback embedding for MVP pipelines.

    TODO: Replace with production embedding model endpoint.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for idx in range(dim):
        value = digest[idx % len(digest)] / 255.0
        values.append(value)
    return values


def build_chunk_records(
    source_key: str,
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
    embedding_dim: int = 16,
) -> list[dict[str, Any]]:
    chunks = chunk_text(text=text, chunk_size=chunk_size, overlap=overlap)
    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        chunk_id = hashlib.sha1(f"{source_key}:{index}".encode("utf-8")).hexdigest()
        records.append(
            {
                "id": chunk_id,
                "text": chunk,
                "embedding": deterministic_embedding(chunk, dim=embedding_dim),
                "metadata": {"source_key": source_key, "chunk_index": index},
            }
        )
    return records


def upsert_chromadb(
    host: str,
    port: int,
    collection_name: str,
    records: list[dict[str, Any]],
) -> int:
    if not records:
        return 0
    import chromadb

    client = chromadb.HttpClient(host=host, port=port)
    collection = client.get_or_create_collection(name=collection_name)
    collection.upsert(
        ids=[record["id"] for record in records],
        documents=[record["text"] for record in records],
        embeddings=[record["embedding"] for record in records],
        metadatas=[record["metadata"] for record in records],
    )
    return len(records)


def upsert_milvus(
    host: str,
    port: int,
    collection_name: str,
    records: list[dict[str, Any]],
    embedding_dim: int = 16,
) -> int:
    if not records:
        return 0

    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )

    connections.connect(alias="default", host=host, port=str(port))
    if not utility.has_collection(collection_name):
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                max_length=128,
                is_primary=True,
                auto_id=False,
            ),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="source_key", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
        ]
        schema = CollectionSchema(fields=fields, description="Pipeline vectorized chunks")
        collection = Collection(name=collection_name, schema=schema)
        collection.create_index(
            field_name="vector",
            index_params={"index_type": "IVF_FLAT", "metric_type": "L2", "params": {"nlist": 128}},
        )
    else:
        collection = Collection(collection_name)

    try:
        collection.upsert(
            [
                [record["id"] for record in records],
                [record["text"] for record in records],
                [record["metadata"].get("source_key", "") for record in records],
                [record["embedding"] for record in records],
            ]
        )
    except Exception:
        # TODO: tighten behavior after Milvus version is pinned cluster-wide.
        collection.insert(
            [
                [record["id"] for record in records],
                [record["text"] for record in records],
                [record["metadata"].get("source_key", "") for record in records],
                [record["embedding"] for record in records],
            ]
        )

    collection.flush()
    return len(records)


def upsert_redis(
    index_name: str,
    records: list[dict[str, Any]],
    *,
    embedding_dim: int = 16,
    metric: str = "cosine",
    algorithm: str = "HNSW",
) -> int:
    """Upsert chunk records into the shared Redis 8 Stack vector store.

    Delegates to :mod:`pipelines.redis_vectors` which owns the
    RediSearch + RedisJSON schema.  The function parallels
    ``upsert_milvus`` / ``upsert_chromadb`` so code can pick a backend
    via configuration (``VECTOR_BACKEND=redis|milvus|chromadb``).
    """
    if not records:
        return 0
    from . import redis_vectors  # local import keeps module import cheap

    redis_vectors.ensure_index(
        index_name,
        vector_dims=embedding_dim,
        metric=metric,
        algorithm=algorithm,
    )
    return redis_vectors.upsert_chunks(index_name, records)

