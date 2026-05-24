#!/usr/bin/env python3
"""Example: Ingest a PDF file into Milvus.

Usage (from repo root):
    python -m pipelines.examples.ingest_pdf_to_milvus \\
        --pdf-path /path/to/document.pdf \\
        --collection rag_documents

Environment variables (or defaults to cluster-internal endpoints):
    PIPELINE_MILVUS_HOST   (default: milvus.data-services)
    PIPELINE_MILVUS_PORT   (default: 19530)
    EMBEDDING_PROVIDER     (default: deterministic)
    EMBEDDING_MODEL        (default: all-MiniLM-L6-v2)
"""

from __future__ import annotations

import argparse
import sys

from pipelines.chunking import chunk_documents
from pipelines.config import PipelineConfig
from pipelines.document_loaders import load_pdf_file
from pipelines.embeddings import EmbeddingProvider
from pipelines.vector_io import upsert_milvus


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDF into Milvus")
    parser.add_argument("--pdf-path", required=True, help="Path to PDF file")
    parser.add_argument("--collection", default="rag_documents", help="Milvus collection name")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=200)
    args = parser.parse_args()

    config = PipelineConfig()
    embedder = EmbeddingProvider()

    print(f"Loading PDF: {args.pdf_path}")
    docs = load_pdf_file(args.pdf_path)
    print(f"  Loaded {len(docs)} pages")

    texts = [d.text for d in docs]
    chunks = chunk_documents(texts, strategy="recursive", chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print(f"  Split into {len(chunks)} chunks")

    import hashlib

    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.embed_texts(chunk_texts)
    records = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        cid = hashlib.sha1(f"{args.pdf_path}:{idx}".encode()).hexdigest()
        records.append({
            "id": cid,
            "text": chunk.text,
            "embedding": emb,
            "metadata": {"source_key": args.pdf_path, "chunk_index": idx},
        })

    count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=args.collection,
        records=records,
        embedding_dim=embedder.dimension,
    )
    print(f"  Upserted {count} records to Milvus collection '{args.collection}'")


if __name__ == "__main__":
    main()
