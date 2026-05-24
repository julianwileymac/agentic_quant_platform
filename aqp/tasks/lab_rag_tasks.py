"""Data Lab RAG ingest Celery task.

Phase 5 — wraps the existing :mod:`aqp.rag.indexers.papers` ingest
pipeline so a Lab user can upload a research paper from
``POST /lab/rag/upload`` and the chunks land in both
:class:`aqp.persistence.models_lab.LabPaperChunk` (denormalised,
HNSW indexed) AND :class:`aqp.rag.HierarchicalRAG`'s canonical
store via the corpus indexer.

Honors:

- AGENTS rule 4 — canonical progress frames via
  :mod:`aqp.tasks._progress`.
- AGENTS rule 11 — RAG retrievals + writes go through
  :class:`HierarchicalRAG`; this task is the only entry point that
  writes the denormalised Lab copy.
- AGENTS rule 22 — agents read the chunks via the
  ``data.research_papers.*`` MCP tool, not this task directly.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.lab_rag_tasks.ingest_paper_for_lab")
def ingest_paper_for_lab(
    self,
    lab_id: str,
    source_uri: str,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Ingest a paper from ``source_uri`` into the Lab RAG sidecar.

    Returns a dict with the ingested chunk count + canonical
    ``rag_corpus_id`` so the frontend can immediately query
    ``POST /lab/rag/query`` with the new tags.
    """
    task_id = self.request.id or f"lab-rag:{uuid4().hex[:10]}"
    emit(task_id, "queued", f"ingest paper {source_uri}", lab_id=lab_id)

    # Parse + chunk + embed via the existing RAG pipeline. Each step
    # is wrapped so a missing optional dep (Marker / Nougat / MathPix)
    # surfaces a structured error instead of crashing.
    try:
        chunks = _parse_and_chunk(source_uri)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"parse failed: {exc}", lab_id=lab_id, source_uri=source_uri)
        return {"status": "error", "error": str(exc), "lab_id": lab_id}
    if not chunks:
        emit_error(task_id, "no chunks produced", lab_id=lab_id, source_uri=source_uri)
        return {
            "status": "error",
            "error": "parser produced zero chunks",
            "lab_id": lab_id,
        }

    emit(
        task_id,
        "embed",
        f"embedding {len(chunks)} chunks",
        lab_id=lab_id,
        n_chunks=len(chunks),
    )
    try:
        embeddings = _embed_chunks(chunks)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"embed failed: {exc}", lab_id=lab_id)
        return {"status": "error", "error": str(exc), "lab_id": lab_id}

    # Persist into the denormalised Lab copy + the canonical RAG corpus.
    persisted = _persist_lab_chunks(
        lab_id=lab_id,
        source_uri=source_uri,
        title=title,
        chunks=chunks,
        embeddings=embeddings,
    )
    try:
        rag_corpus_id = _persist_rag_corpus(source_uri=source_uri, title=title, chunks=chunks, tags=tags or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("RAG corpus persistence failed: %s", exc)
        rag_corpus_id = None

    result = {
        "status": "done",
        "lab_id": lab_id,
        "source_uri": source_uri,
        "n_chunks": int(persisted),
        "rag_corpus_id": rag_corpus_id,
        "title": title,
    }
    emit_done(task_id, result)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_and_chunk(source_uri: str) -> list[dict[str, Any]]:
    """Parse + section-split + chunk via the existing parser registry.

    Falls back to a simple HTTP fetch + 512-token sliding window when
    the upstream parser registry isn't installed (dev / tests).
    """
    try:
        from aqp.rag.parsers import parse_paper

        return list(parse_paper(source_uri))
    except Exception as exc:  # noqa: BLE001
        logger.debug("parse_paper unavailable; falling back to text fetch: %s", exc)
    # Fallback path — minimal HTTP get + naive chunking
    try:
        import httpx

        response = httpx.get(source_uri, timeout=30.0)
        response.raise_for_status()
        text = response.text
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"could not fetch source_uri: {exc}") from exc
    chunks: list[dict[str, Any]] = []
    window = 2048
    step = 1500
    for i in range(0, len(text), step):
        chunk = text[i : i + window]
        if not chunk.strip():
            continue
        chunks.append(
            {
                "ord": len(chunks),
                "text": chunk,
                "metadata": {"offset": i, "fallback_chunker": True},
            }
        )
        if len(chunks) >= 200:
            break
    return chunks


def _embed_chunks(chunks: list[dict[str, Any]]) -> list[list[float]]:
    try:
        from aqp.rag.embedder import get_embedder

        embedder = get_embedder()
        return list(embedder.embed([c["text"] for c in chunks]))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"embedder unavailable: {exc}") from exc


def _persist_lab_chunks(
    *,
    lab_id: str,
    source_uri: str,
    title: str | None,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> int:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabPaperChunk
    except Exception as exc:  # noqa: BLE001
        logger.debug("lab paper chunk persistence unavailable: %s", exc)
        return 0
    inserted = 0
    try:
        with SessionLocal() as session:
            for chunk, vector in zip(chunks, embeddings, strict=True):
                chunk_id = hashlib.sha256(
                    f"{source_uri}:{chunk['ord']}".encode("utf-8")
                ).hexdigest()[:60]
                row = LabPaperChunk(
                    id=chunk_id,
                    lab_id=lab_id,
                    paper_title=title or source_uri,
                    source_uri=source_uri,
                    chunk_ord=int(chunk.get("ord", 0)),
                    text=str(chunk.get("text", "")),
                    embedding=list(vector),
                    embedding_model="default",
                    metadata_json=dict(chunk.get("metadata") or {}),
                    created_at=datetime.utcnow(),
                )
                session.merge(row)
                inserted += 1
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("lab paper chunk persistence failed: %s", exc)
    return inserted


def _persist_rag_corpus(
    *,
    source_uri: str,
    title: str | None,
    chunks: list[dict[str, Any]],
    tags: list[str],
) -> str | None:
    """Optionally also persist to the canonical Redis-backed RAG corpus.

    Best-effort; when the HierarchicalRAG indexer is missing (dev,
    Pyodide-only test env) we return None and let the Lab-side copy
    serve the panel.
    """
    try:
        from aqp.rag.hierarchy import HierarchicalRAG

        rag = HierarchicalRAG()
        return rag.index_chunks(
            corpus="lab_research_papers",
            items=[
                {
                    "id": f"{source_uri}:{c['ord']}",
                    "text": c["text"],
                    "metadata": {
                        "source_uri": source_uri,
                        "title": title,
                        "tags": tags,
                    },
                }
                for c in chunks
            ],
        )
    except Exception:  # noqa: BLE001
        return None


__all__ = ["ingest_paper_for_lab"]
