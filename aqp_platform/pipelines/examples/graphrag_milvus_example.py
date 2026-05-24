#!/usr/bin/env python3
"""Example: Build a GraphRAG knowledge base in Milvus.

Creates three Milvus collections (entities, relations, passages) from
a text file, inspired by RAG_Techniques graphrag_with_milvus_vectordb.

Usage:
    python -m pipelines.examples.graphrag_milvus_example \\
        --input-path /path/to/document.txt

Environment variables:
    PIPELINE_MILVUS_HOST   (default: milvus.data-services)
    PIPELINE_MILVUS_PORT   (default: 19530)
    EMBEDDING_PROVIDER     (default: deterministic)
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from pipelines.chunking import chunk_documents
from pipelines.config import PipelineConfig
from pipelines.embeddings import EmbeddingProvider
from pipelines.vector_io import upsert_milvus


def main() -> None:
    parser = argparse.ArgumentParser(description="GraphRAG → Milvus example")
    parser.add_argument("--input-path", required=True, help="Path to source text file")
    parser.add_argument("--entities-collection", default="graphrag_entities")
    parser.add_argument("--relations-collection", default="graphrag_relations")
    parser.add_argument("--passages-collection", default="graphrag_passages")
    args = parser.parse_args()

    config = PipelineConfig()
    embedder = EmbeddingProvider()

    text = Path(args.input_path).read_text(encoding="utf-8", errors="replace")
    source_key = str(args.input_path)
    print(f"Loaded {len(text)} characters from {source_key}")

    # --- Entity extraction (rule-based; replace with LLM for production) ---
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 20]
    entities: list[dict] = []
    relations: list[dict] = []
    seen: set[str] = set()

    for sent in sentences[:500]:
        words = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", sent)
        for w in words:
            if w not in seen:
                seen.add(w)
                eid = hashlib.sha1(w.encode()).hexdigest()[:16]
                entities.append({
                    "id": eid, "text": w,
                    "embedding": embedder.embed_text(w),
                    "metadata": {"source_key": source_key, "type": "entity"},
                })
        unique = list(set(words))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                rid = hashlib.sha1(f"{unique[i]}:{unique[j]}".encode()).hexdigest()[:16]
                rel_text = f"{unique[i]} -- related_to -- {unique[j]}"
                relations.append({
                    "id": rid, "text": rel_text,
                    "embedding": embedder.embed_text(rel_text),
                    "metadata": {"source_key": source_key, "type": "relation"},
                })

    print(f"  Extracted {len(entities)} entities, {len(relations)} relations")

    # --- Passage chunking ---
    chunks = chunk_documents([text], strategy="recursive", chunk_size=800, chunk_overlap=200)
    chunk_texts = [c.text for c in chunks]
    embs = embedder.embed_texts(chunk_texts)
    passages = [
        {
            "id": hashlib.sha1(f"{source_key}:p:{i}".encode()).hexdigest(),
            "text": c.text,
            "embedding": e,
            "metadata": {"source_key": source_key, "chunk_index": i},
        }
        for i, (c, e) in enumerate(zip(chunks, embs))
    ]
    print(f"  Created {len(passages)} passage chunks")

    # --- Upsert to Milvus ---
    ec = upsert_milvus(config.milvus_host, config.milvus_port,
                        args.entities_collection, entities, embedder.dimension)
    rc = upsert_milvus(config.milvus_host, config.milvus_port,
                        args.relations_collection, relations, embedder.dimension)
    pc = upsert_milvus(config.milvus_host, config.milvus_port,
                        args.passages_collection, passages, embedder.dimension)
    print(f"  Milvus upserts — entities: {ec}, relations: {rc}, passages: {pc}")


if __name__ == "__main__":
    main()
