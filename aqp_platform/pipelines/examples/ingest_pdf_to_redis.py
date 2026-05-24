#!/usr/bin/env python3
"""Example: ingest a PDF into the shared Redis 8 Stack vector store.

Usage (from repo root)::

    python -m pipelines.examples.ingest_pdf_to_redis \
        --pdf-path /path/to/document.pdf \
        --index idx:chunks

Environment variables (with sensible defaults pointing at the in-cluster
Redis service)::

    REDIS_URL              redis://:ragflow123@redis.data-services...:6379/0
    REDIS_INDEX_PREFIX     rpi
    EMBEDDING_PROVIDER     deterministic | sentence_transformers | openai
    EMBEDDING_MODEL        all-MiniLM-L6-v2
"""

from __future__ import annotations

import argparse
import hashlib
import os

from pipelines.chunking import chunk_documents
from pipelines.document_loaders import load_pdf_file
from pipelines.embeddings import EmbeddingProvider
from pipelines.redis_io import ping, require_modules
from pipelines.redis_vectors import ensure_index, upsert_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a PDF into Redis Stack")
    parser.add_argument("--pdf-path", required=True)
    parser.add_argument("--index", default="idx:chunks")
    parser.add_argument("--collection", default="general")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    args = parser.parse_args()

    if not ping():
        raise SystemExit("Cannot reach Redis. Check REDIS_URL / REDIS_PASSWORD.")
    require_modules(("search", "rejson"))

    embedder = EmbeddingProvider()

    print(f"Loading PDF: {args.pdf_path}")
    pages = load_pdf_file(args.pdf_path)
    print(f"  Loaded {len(pages)} pages")

    chunks = chunk_documents(
        [p.text for p in pages],
        strategy="recursive",
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(f"  Split into {len(chunks)} chunks")

    embeddings = embedder.embed_texts([c.text for c in chunks])
    ensure_index(args.index, vector_dims=embedder.dimension)

    base = os.path.basename(args.pdf_path)
    records = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        cid = hashlib.sha1(f"{args.pdf_path}:{idx}".encode()).hexdigest()
        records.append(
            {
                "id": cid,
                "text": chunk.text,
                "embedding": list(emb),
                "metadata": {
                    "source_key": base,
                    "doc_id": base,
                    "collection": args.collection,
                    "chunk_index": idx,
                },
            }
        )

    written = upsert_chunks(args.index, records)
    print(f"  Upserted {written} chunks to Redis index '{args.index}'")


if __name__ == "__main__":
    main()
