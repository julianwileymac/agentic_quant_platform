#!/usr/bin/env python3
"""Example: Hybrid search (BM25 + vector) across Milvus and ChromaDB.

Usage:
    python -m pipelines.examples.hybrid_search_example \\
        --query "What is machine learning?" \\
        --collection rag_documents

Environment variables:
    PIPELINE_MILVUS_HOST / PIPELINE_CHROMA_HOST
    EMBEDDING_PROVIDER / EMBEDDING_MODEL
"""

from __future__ import annotations

import argparse

from pipelines.config import PipelineConfig
from pipelines.embeddings import EmbeddingProvider
from pipelines.retrieval import (
    chromadb_vector_search,
    hybrid_search_milvus,
    milvus_vector_search,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid search example")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--collection", default="rag_documents", help="Collection name")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--backend", choices=["milvus", "chromadb", "both"], default="both")
    args = parser.parse_args()

    config = PipelineConfig()
    embedder = EmbeddingProvider()
    query_vec = embedder.embed_text(args.query)

    if args.backend in ("milvus", "both"):
        print(f"\n=== Milvus vector search (collection: {args.collection}) ===")
        results = milvus_vector_search(
            host=config.milvus_host, port=config.milvus_port,
            collection_name=args.collection, query_vector=query_vec, top_k=args.top_k,
        )
        for i, r in enumerate(results):
            print(f"  [{i+1}] score={r.score:.4f}  text={r.text[:120]}...")

    if args.backend in ("chromadb", "both"):
        print(f"\n=== ChromaDB vector search (collection: {args.collection}) ===")
        results = chromadb_vector_search(
            host=config.chroma_host, port=config.chroma_port,
            collection_name=args.collection, query_embedding=query_vec, top_k=args.top_k,
        )
        for i, r in enumerate(results):
            print(f"  [{i+1}] score={r.score:.4f}  text={r.text[:120]}...")

    print("\nDone.")


if __name__ == "__main__":
    main()
