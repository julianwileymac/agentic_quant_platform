"""Retrieval helpers: hybrid search, BM25, reranking for Milvus and ChromaDB."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    """A single search result."""

    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


def bm25_search(
    query: str,
    corpus: list[str],
    top_k: int = 10,
) -> list[SearchResult]:
    """BM25 keyword search over a local corpus."""
    from rank_bm25 import BM25Okapi

    tokenized = [doc.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())

    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        SearchResult(text=corpus[idx], score=float(score), metadata={"bm25_rank": rank})
        for rank, (idx, score) in enumerate(ranked)
        if score > 0
    ]


def milvus_vector_search(
    host: str,
    port: int,
    collection_name: str,
    query_vector: list[float],
    top_k: int = 10,
    output_fields: list[str] | None = None,
) -> list[SearchResult]:
    """Dense vector search against a Milvus collection."""
    from pymilvus import Collection, connections

    connections.connect(alias="default", host=host, port=str(port))
    collection = Collection(collection_name)
    collection.load()

    results = collection.search(
        data=[query_vector],
        anns_field="vector",
        param={"metric_type": "L2", "params": {"nprobe": 16}},
        limit=top_k,
        output_fields=output_fields or ["text", "source_key"],
    )

    search_results: list[SearchResult] = []
    for hits in results:
        for rank, hit in enumerate(hits):
            entity = hit.entity
            search_results.append(
                SearchResult(
                    text=entity.get("text", ""),
                    score=float(hit.distance),
                    metadata={
                        "source_key": entity.get("source_key", ""),
                        "milvus_rank": rank,
                        "id": str(hit.id),
                    },
                )
            )
    return search_results


def chromadb_vector_search(
    host: str,
    port: int,
    collection_name: str,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[SearchResult]:
    """Dense vector search against a ChromaDB collection."""
    import chromadb

    client = chromadb.HttpClient(host=host, port=port)
    collection = client.get_or_create_collection(name=collection_name)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "distances", "metadatas"],
    )

    search_results: list[SearchResult] = []
    if results["documents"]:
        for rank, (doc, dist, meta) in enumerate(
            zip(
                results["documents"][0],
                results["distances"][0],
                results["metadatas"][0],
            )
        ):
            search_results.append(
                SearchResult(
                    text=doc or "",
                    score=float(dist),
                    metadata={**(meta or {}), "chromadb_rank": rank},
                )
            )
    return search_results


def redis_vector_search(
    index_name: str,
    query_vector: list[float],
    top_k: int = 10,
    filters: str | None = None,
) -> list[SearchResult]:
    """Dense vector search against a Redis 8 Stack RediSearch index.

    Delegates to :mod:`pipelines.redis_vectors` and reshapes the hits
    into :class:`SearchResult` so callers can mix-and-match with
    Milvus/ChromaDB results in hybrid search or RRF.
    """
    from . import redis_vectors

    hits = redis_vectors.vector_search(
        index_name=index_name,
        query_vector=query_vector,
        top_k=top_k,
        filters=filters,
    )
    return [
        SearchResult(
            text=hit.text,
            score=float(hit.score),
            metadata={**hit.metadata, "redis_rank": rank, "id": hit.id},
        )
        for rank, hit in enumerate(hits)
    ]


def hybrid_search_redis(
    index_name: str,
    query: str,
    query_vector: list[float],
    corpus: list[str] | None = None,
    top_k: int = 10,
    filters: str | None = None,
) -> list[SearchResult]:
    """Hybrid search combining BM25 + Redis dense retrieval via RRF."""
    vector_results = redis_vector_search(
        index_name=index_name,
        query_vector=query_vector,
        top_k=top_k,
        filters=filters,
    )
    if corpus:
        bm25_results = bm25_search(query=query, corpus=corpus, top_k=top_k)
        return reciprocal_rank_fusion(vector_results, bm25_results, top_k=top_k)
    return vector_results


def reciprocal_rank_fusion(
    *result_lists: list[SearchResult],
    k: int = 60,
    top_k: int = 10,
) -> list[SearchResult]:
    """Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.

    Uses the formula: score = sum(1 / (k + rank)) across all lists.
    """
    scores: dict[str, float] = {}
    text_map: dict[str, SearchResult] = {}

    for result_list in result_lists:
        for rank, result in enumerate(result_list):
            doc_key = result.text[:200]
            scores[doc_key] = scores.get(doc_key, 0.0) + 1.0 / (k + rank + 1)
            if doc_key not in text_map:
                text_map[doc_key] = result

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        SearchResult(
            text=text_map[key].text,
            score=score,
            metadata={**text_map[key].metadata, "rrf_score": score},
        )
        for key, score in ranked
    ]


def hybrid_search_milvus(
    host: str,
    port: int,
    collection_name: str,
    query: str,
    query_vector: list[float],
    corpus: list[str] | None = None,
    top_k: int = 10,
    alpha: float = 0.5,
) -> list[SearchResult]:
    """Hybrid search combining BM25 + Milvus dense retrieval via RRF.

    If *corpus* is None, only vector search is performed.
    *alpha* controls the blend (not used directly with RRF but reserved
    for weighted-sum alternatives).
    """
    vector_results = milvus_vector_search(
        host=host, port=port, collection_name=collection_name,
        query_vector=query_vector, top_k=top_k,
    )

    if corpus:
        bm25_results = bm25_search(query=query, corpus=corpus, top_k=top_k)
        return reciprocal_rank_fusion(vector_results, bm25_results, top_k=top_k)

    return vector_results


def hybrid_search_chromadb(
    host: str,
    port: int,
    collection_name: str,
    query: str,
    query_embedding: list[float],
    corpus: list[str] | None = None,
    top_k: int = 10,
) -> list[SearchResult]:
    """Hybrid search combining BM25 + ChromaDB dense retrieval via RRF."""
    vector_results = chromadb_vector_search(
        host=host, port=port, collection_name=collection_name,
        query_embedding=query_embedding, top_k=top_k,
    )

    if corpus:
        bm25_results = bm25_search(query=query, corpus=corpus, top_k=top_k)
        return reciprocal_rank_fusion(vector_results, bm25_results, top_k=top_k)

    return vector_results
