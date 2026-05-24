#!/usr/bin/env python3
"""Example: Ingest CSV data into Milvus.

Usage (from repo root):
    python -m pipelines.examples.ingest_csv_to_milvus \\
        --csv-path /path/to/data.csv \\
        --collection rag_csv_data \\
        --text-columns "description,notes"

Environment variables:
    PIPELINE_MILVUS_HOST   (default: milvus.data-services)
    PIPELINE_MILVUS_PORT   (default: 19530)
    EMBEDDING_PROVIDER     (default: deterministic)
"""

from __future__ import annotations

import argparse
import hashlib

from pipelines.chunking import chunk_documents
from pipelines.config import PipelineConfig
from pipelines.document_loaders import load_csv_file
from pipelines.embeddings import EmbeddingProvider
from pipelines.vector_io import upsert_milvus


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest CSV into Milvus")
    parser.add_argument("--csv-path", required=True, help="Path to CSV file")
    parser.add_argument("--collection", default="rag_csv_data", help="Milvus collection name")
    parser.add_argument("--text-columns", default="", help="Comma-separated column names to use as document text")
    parser.add_argument("--chunk-size", type=int, default=800)
    args = parser.parse_args()

    config = PipelineConfig()
    embedder = EmbeddingProvider()
    text_cols = [c.strip() for c in args.text_columns.split(",") if c.strip()] or None

    print(f"Loading CSV: {args.csv_path}")
    docs = load_csv_file(args.csv_path, text_columns=text_cols)
    print(f"  Loaded {len(docs)} rows")

    texts = [d.text for d in docs]
    chunks = chunk_documents(texts, strategy="recursive", chunk_size=args.chunk_size, chunk_overlap=100)
    print(f"  Split into {len(chunks)} chunks")

    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.embed_texts(chunk_texts)
    records = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        cid = hashlib.sha1(f"{args.csv_path}:{idx}".encode()).hexdigest()
        records.append({
            "id": cid,
            "text": chunk.text,
            "embedding": emb,
            "metadata": {"source_key": args.csv_path, "chunk_index": idx},
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
