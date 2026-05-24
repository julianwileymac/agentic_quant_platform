#!/usr/bin/env python3
"""Example: ingest a JSON artifact from MinIO into the Redis document store.

Designed to mirror the "Ingest" button in the document portal: it pulls
an object from a MinIO bucket, flattens nested structures, chunks, and
upserts.  Useful for plumbing data lake artifacts into the unified
agent / RAG layer without making them go through Dagster first.

Usage::

    python -m pipelines.examples.ingest_minio_json_to_redis \
        --bucket dagster-artifacts \
        --key normalized/snapshot.json \
        --collection mlops --tag snapshot --tag dagster

Environment::

    PIPELINE_MINIO_*  -- MinIO connection (see pipelines.config.PipelineConfig)
    REDIS_URL         -- defaults to in-cluster shared instance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from pipelines.chunking import chunk_documents
from pipelines.config import PipelineConfig
from pipelines.embeddings import EmbeddingProvider
from pipelines.minio_io import get_minio_client
from pipelines.redis_io import ping, require_modules
from pipelines.redis_vectors import ensure_index, upsert_chunks


def _flatten(obj, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            lines.extend(_flatten(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            lines.extend(_flatten(v, f"{prefix}[{i}]"))
    else:
        lines.append(f"{prefix}: {obj}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest MinIO JSON into Redis")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--index", default="idx:chunks")
    parser.add_argument("--collection", default="general")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    args = parser.parse_args()

    if not ping():
        raise SystemExit("Cannot reach Redis. Check REDIS_URL / REDIS_PASSWORD.")
    require_modules(("search", "rejson"))

    cfg = PipelineConfig()
    s3 = get_minio_client(cfg)
    print(f"Fetching s3://{args.bucket}/{args.key}")
    body = s3.get_object(Bucket=args.bucket, Key=args.key)["Body"].read()

    parsed = json.loads(body.decode("utf-8"))
    text = "\n".join(_flatten(parsed))
    print(f"  Flattened to {len(text):,} chars")

    chunks = chunk_documents(
        [text],
        strategy="recursive",
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print(f"  Split into {len(chunks)} chunks")

    embedder = EmbeddingProvider()
    embeddings = embedder.embed_texts([c.text for c in chunks])
    ensure_index(args.index, vector_dims=embedder.dimension)

    doc_id = hashlib.sha256(f"{args.bucket}/{args.key}".encode()).hexdigest()[:16]
    records = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        cid = hashlib.sha1(f"{args.bucket}/{args.key}:{idx}".encode()).hexdigest()
        records.append(
            {
                "id": cid,
                "text": chunk.text,
                "embedding": list(emb),
                "metadata": {
                    "doc_id": doc_id,
                    "source": "minio-artifact",
                    "source_key": f"s3://{args.bucket}/{args.key}",
                    "collection": args.collection,
                    "chunk_index": idx,
                    "tags": args.tag,
                },
            }
        )

    written = upsert_chunks(args.index, records)
    print(f"  Upserted {written} chunks for doc {doc_id} to Redis '{args.index}'")


if __name__ == "__main__":
    main()
