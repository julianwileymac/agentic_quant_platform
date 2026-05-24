"""Dagster assets for RAG document ingestion into Milvus and ChromaDB.

Provides:
 - PDF document ingestion
 - CSV data ingestion
 - GraphRAG knowledge base building (entity/relation/passage to Milvus)
 - Hybrid search index refresh
"""

from __future__ import annotations

from dagster import Field, MetadataValue, asset

from pipelines.chunking import chunk_documents
from pipelines.config import PipelineConfig
from pipelines.document_loaders import load_minio_object
from pipelines.embeddings import EmbeddingProvider
from pipelines.vector_io import upsert_chromadb, upsert_milvus


def _embed_and_build_records(
    texts: list[str],
    source_key: str,
    embedder: EmbeddingProvider,
) -> list[dict]:
    """Chunk, embed, and build upsert-ready records."""
    import hashlib

    chunks = chunk_documents(texts, strategy="recursive", chunk_size=800, chunk_overlap=200)
    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.embed_texts(chunk_texts)

    records: list[dict] = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        chunk_id = hashlib.sha1(f"{source_key}:{idx}".encode("utf-8")).hexdigest()
        records.append(
            {
                "id": chunk_id,
                "text": chunk.text,
                "embedding": embedding,
                "metadata": {
                    "source_key": source_key,
                    "chunk_index": idx,
                    **chunk.metadata,
                },
            }
        )
    return records


@asset(
    config_schema={
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "source_prefix": Field(str, default_value="raw/documents/"),
        "source_key": Field(str, default_value=""),
        "collection_name": Field(str, default_value="rag_documents"),
        "embedding_provider": Field(str, default_value="deterministic"),
        "embedding_model": Field(str, default_value="all-MiniLM-L6-v2"),
    },
    description="Ingest PDF documents from MinIO into Milvus and ChromaDB vector stores.",
)
def ingest_pdf_documents(context):
    config = PipelineConfig()
    op = context.op_config
    embedder = EmbeddingProvider(
        provider=op["embedding_provider"],
        model_name=op["embedding_model"],
    )

    source_key = op["source_key"]
    if not source_key:
        context.log.warning("No source_key specified; skipping ingestion")
        return {"status": "skipped", "reason": "no source_key"}

    docs = load_minio_object(config, bucket=op["source_bucket"], key=source_key)
    if not docs:
        return {"status": "ok", "chunk_count": 0}

    texts = [d.text for d in docs]
    records = _embed_and_build_records(texts, source_key, embedder)

    milvus_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=op["collection_name"],
        records=records,
        embedding_dim=embedder.dimension,
    )
    chroma_count = upsert_chromadb(
        host=config.chroma_host,
        port=config.chroma_port,
        collection_name=op["collection_name"],
        records=records,
    )

    context.add_output_metadata(
        {
            "source_key": MetadataValue.text(source_key),
            "pages_loaded": len(docs),
            "chunk_count": len(records),
            "milvus_upserts": milvus_count,
            "chromadb_upserts": chroma_count,
        }
    )
    return {
        "status": "ok",
        "chunk_count": len(records),
        "milvus_upserts": milvus_count,
        "chromadb_upserts": chroma_count,
    }


@asset(
    config_schema={
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "source_key": Field(str, default_value=""),
        "text_columns": Field(str, default_value=""),
        "collection_name": Field(str, default_value="rag_csv_data"),
        "embedding_provider": Field(str, default_value="deterministic"),
        "embedding_model": Field(str, default_value="all-MiniLM-L6-v2"),
    },
    description="Ingest CSV data from MinIO into Milvus and ChromaDB.",
)
def ingest_csv_data(context):
    config = PipelineConfig()
    op = context.op_config
    embedder = EmbeddingProvider(
        provider=op["embedding_provider"],
        model_name=op["embedding_model"],
    )

    source_key = op["source_key"]
    if not source_key:
        context.log.warning("No source_key specified; skipping ingestion")
        return {"status": "skipped"}

    from pipelines.document_loaders import load_csv_bytes
    from pipelines.minio_io import get_bytes, get_minio_client

    client = get_minio_client(config)
    data = get_bytes(client=client, bucket=op["source_bucket"], key=source_key)
    text_cols = [c.strip() for c in op["text_columns"].split(",") if c.strip()] or None
    docs = load_csv_bytes(data, source_name=source_key, text_columns=text_cols)

    if not docs:
        return {"status": "ok", "row_count": 0}

    texts = [d.text for d in docs]
    records = _embed_and_build_records(texts, source_key, embedder)

    milvus_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=op["collection_name"],
        records=records,
        embedding_dim=embedder.dimension,
    )
    chroma_count = upsert_chromadb(
        host=config.chroma_host,
        port=config.chroma_port,
        collection_name=op["collection_name"],
        records=records,
    )

    context.add_output_metadata(
        {
            "source_key": MetadataValue.text(source_key),
            "rows_loaded": len(docs),
            "chunk_count": len(records),
            "milvus_upserts": milvus_count,
            "chromadb_upserts": chroma_count,
        }
    )
    return {
        "status": "ok",
        "row_count": len(docs),
        "chunk_count": len(records),
    }


@asset(
    config_schema={
        "source_bucket": Field(str, default_value="dagster-artifacts"),
        "source_key": Field(str, default_value=""),
        "entities_collection": Field(str, default_value="graphrag_entities"),
        "relations_collection": Field(str, default_value="graphrag_relations"),
        "passages_collection": Field(str, default_value="graphrag_passages"),
        "embedding_provider": Field(str, default_value="deterministic"),
        "embedding_model": Field(str, default_value="all-MiniLM-L6-v2"),
    },
    description="Build a GraphRAG knowledge base with entities, relations, and passages in Milvus.",
)
def graphrag_knowledge_base(context):
    """Extract entities/relations/passages and store in separate Milvus collections.

    Inspired by RAG_Techniques graphrag_with_milvus_vectordb.ipynb.
    For production, replace the rule-based extraction with an LLM call.
    """
    import hashlib
    import json
    import re

    config = PipelineConfig()
    op = context.op_config
    embedder = EmbeddingProvider(
        provider=op["embedding_provider"],
        model_name=op["embedding_model"],
    )

    source_key = op["source_key"]
    if not source_key:
        return {"status": "skipped"}

    docs = load_minio_object(config, bucket=op["source_bucket"], key=source_key)
    full_text = "\n\n".join(d.text for d in docs)

    sentences = [s.strip() for s in re.split(r"[.!?]\s+", full_text) if len(s.strip()) > 20]

    entities: list[dict] = []
    relations: list[dict] = []
    seen_entities: set[str] = set()

    for sent in sentences[:500]:
        words = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", sent)
        for word in words:
            if word not in seen_entities:
                seen_entities.add(word)
                eid = hashlib.sha1(word.encode()).hexdigest()[:16]
                emb = embedder.embed_text(word)
                entities.append(
                    {
                        "id": eid,
                        "text": word,
                        "embedding": emb,
                        "metadata": {"source_key": source_key, "type": "entity"},
                    }
                )
        entity_list = list(set(words))
        for i in range(len(entity_list)):
            for j in range(i + 1, len(entity_list)):
                rid = hashlib.sha1(f"{entity_list[i]}:{entity_list[j]}".encode()).hexdigest()[:16]
                rel_text = f"{entity_list[i]} -- related_to -- {entity_list[j]}"
                emb = embedder.embed_text(rel_text)
                relations.append(
                    {
                        "id": rid,
                        "text": rel_text,
                        "embedding": emb,
                        "metadata": {
                            "source_key": source_key,
                            "source_entity": entity_list[i],
                            "target_entity": entity_list[j],
                            "type": "relation",
                        },
                    }
                )

    texts = [d.text for d in docs]
    passage_records = _embed_and_build_records(texts, source_key, embedder)

    entity_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=op["entities_collection"],
        records=entities,
        embedding_dim=embedder.dimension,
    )
    relation_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=op["relations_collection"],
        records=relations,
        embedding_dim=embedder.dimension,
    )
    passage_count = upsert_milvus(
        host=config.milvus_host,
        port=config.milvus_port,
        collection_name=op["passages_collection"],
        records=passage_records,
        embedding_dim=embedder.dimension,
    )

    context.add_output_metadata(
        {
            "entities": entity_count,
            "relations": relation_count,
            "passages": passage_count,
        }
    )
    return {
        "status": "ok",
        "entities": entity_count,
        "relations": relation_count,
        "passages": passage_count,
    }
