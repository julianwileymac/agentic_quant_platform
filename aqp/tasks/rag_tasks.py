"""Celery tasks for hierarchical RAG indexing + Raptor summarisation."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.rag_tasks.index_corpus")
def index_corpus(self, corpus: str, **kwargs: Any) -> dict[str, Any]:
    """Run the registered indexer for a single corpus."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Indexing corpus {corpus}")
    try:
        from aqp.rag.indexers import get_indexer

        fn = get_indexer(corpus)
        n = fn(**kwargs)
        result = {"corpus": corpus, "indexed": int(n)}
        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("index_corpus failed for %s", corpus)
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.rag_tasks.refresh_l0_alpha_base")
def refresh_l0_alpha_base(
    self,
    *,
    limit: int = 5000,
    since_days: int | None = 365,
) -> dict[str, Any]:
    """Re-index the L0 alpha / decision base (paper RAG#0)."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "Refreshing L0 alpha base")
    try:
        from aqp.rag.indexers import index_decisions, index_performance

        decisions_n = index_decisions(limit=limit, since_days=since_days)
        performance_n = index_performance(limit=limit)
        result = {"decisions": int(decisions_n), "performance": int(performance_n)}
        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("refresh_l0_alpha_base failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.rag_tasks.refresh_hierarchy")
def refresh_hierarchy(self, corpora: list[str] | None = None) -> dict[str, Any]:
    """Re-index every (or a subset of) registered corpora at L2/L3."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "Refreshing hierarchy")
    try:
        from aqp.rag.indexers import INDEXER_REGISTRY

        targets = corpora or list(INDEXER_REGISTRY)
        out: dict[str, int] = {}
        for c in targets:
            try:
                fn = INDEXER_REGISTRY[c]
            except KeyError:
                continue
            try:
                out[c] = int(fn())
            except Exception:  # noqa: BLE001
                logger.exception("Indexer %s failed", c)
                out[c] = 0
            emit(task_id, "progress", f"Indexed {c}: {out[c]}")
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        logger.exception("refresh_hierarchy failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.rag_tasks.raptor_summarize")
def raptor_summarize(
    self,
    corpus: str,
    *,
    level_target: str = "l2",
    max_levels: int = 3,
    k_max: int = 8,
    sample_size: int = 256,
) -> dict[str, Any]:
    """Build a Raptor summary tree on top of an existing corpus.

    Pulls up to ``sample_size`` leaf chunks from the corpus, runs UMAP +
    GMM + LLM-summary at ``max_levels`` recursive cluster levels, and
    writes the resulting summary nodes back into Redis at
    ``level_target`` (l1 by default).
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Raptor summarising corpus={corpus}")
    try:
        from aqp.rag import get_default_rag
        from aqp.rag.embedder import get_embedder
        from aqp.rag.raptor import build_tree

        rag = get_default_rag()
        embedder = get_embedder()
        # Pull leaves via direct vector search using a synthetic neutral query.
        seeds = rag.query(
            "summary",
            level="l3",
            corpus=corpus,
            k=sample_size,
            rerank=False,
            compress=False,
        )
        if not seeds:
            emit_done(task_id, {"corpus": corpus, "leaves": 0, "summaries": 0})
            return {"corpus": corpus, "leaves": 0, "summaries": 0}
        leaf_ids = [h.doc_id for h in seeds]
        leaf_texts = [h.text for h in seeds]
        leaf_vectors = embedder.embed(leaf_texts)
        tree = build_tree(
            leaf_ids=leaf_ids,
            leaf_texts=leaf_texts,
            leaf_vectors=leaf_vectors,
            max_levels=max_levels,
            k_max=k_max,
        )
        summary_count = 0
        for _node_id, node in tree.nodes.items():
            try:
                rag.index_summary(
                    corpus,
                    level=level_target,
                    text=node.text,
                    member_ids=node.member_ids,
                    meta={"raptor_level": node.level, "cluster_id": node.cluster_id},
                )
                summary_count += 1
            except Exception:  # noqa: BLE001
                logger.exception("Failed to write Raptor summary node")
        result = {
            "corpus": corpus,
            "leaves": len(leaf_ids),
            "summaries": summary_count,
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("raptor_summarize failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.rag_tasks.evaluate_rag")
def evaluate_rag(
    self,
    queries: list[str],
    *,
    level: str = "l3",
    k: int = 8,
) -> dict[str, Any]:
    """Lightweight retrieval audit — record k hits per query in rag_eval_runs."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Evaluating RAG over {len(queries)} queries")
    try:
        from aqp.rag import get_default_rag

        rag = get_default_rag()
        results: list[dict[str, Any]] = []
        for q in queries:
            hits = rag.query(q, level=level, k=k)
            results.append(
                {
                    "query": q,
                    "n_hits": len(hits),
                    "top_score": float(hits[0].score) if hits else None,
                    "ids": [h.doc_id for h in hits],
                }
            )
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rag import RagEvalRun

            with SessionLocal() as session:
                session.add(RagEvalRun(level=level, k=k, results=results, n_queries=len(queries)))
                session.commit()
        except Exception:  # pragma: no cover
            logger.debug("RAG eval persistence unavailable", exc_info=True)
        emit_done(task_id, {"queries": len(queries), "results": results})
        return {"queries": len(queries), "results": results}
    except Exception as exc:  # pragma: no cover
        logger.exception("evaluate_rag failed")
        emit_error(task_id, str(exc))
        raise
