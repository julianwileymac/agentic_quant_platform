"""Celery tasks for the math-aware research-paper RAG.

Two tasks:

- :func:`ingest_research_paper` — parse a single uploaded PDF, write
  the corresponding ``ResearchPaperRow`` updates (title / equations
  count / parser used) and feed chunks through
  :func:`aqp.rag.indexers.research_papers_indexer.index_research_papers`.
- :func:`synthesize_strategy_from_paper` — call
  :func:`aqp.llm.providers.router.router_complete` (AGENTS.md rule 2)
  with the paper's top chunks + a "act as a quant developer" system
  prompt; return a YAML strategy stub the composer can load.

Both tasks emit progress through
:mod:`aqp.tasks._progress` (AGENTS.md rule 4) and are idempotent on
``paper_id`` (AGENTS.md rule 5).
"""
from __future__ import annotations

import logging
import textwrap
import uuid
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.research_paper_tasks.ingest_research_paper")
def ingest_research_paper(self, *, paper_id: str) -> dict[str, Any]:
    """Parse the PDF and feed its chunks into HierarchicalRAG."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Ingesting research paper {paper_id}")
    try:
        from aqp.rag.indexers.research_papers_indexer import index_research_papers

        emit(task_id, "parsing", "Selecting parser + extracting text + equations")
        written = index_research_papers(paper_ids=[paper_id])
        result = {"paper_id": paper_id, "chunks_written": int(written)}
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest_research_paper failed")
        emit_error(task_id, str(exc))
        raise


_SYNTH_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a senior quantitative strategy developer. Read the
    excerpts from the research paper below and emit a valid AQP
    strategy YAML following the `{class, module_path, kwargs}`
    factory pattern. Use existing AQP alpha / risk / portfolio /
    execution / universe classes wherever possible. Output:

    1) A short rationale (2-3 sentences) explaining the mapping.
    2) The YAML wrapped in ```yaml fences```.

    Never invent class names that aren't in the AQP registry. Prefer
    `FrameworkAlgorithm` as the top-level class.
    """
).strip()


def synthesize_strategy_impl(paper_id: str) -> dict[str, Any]:
    """Sync implementation of the synthesis pipeline.

    Imported by both the Celery task wrapper below and the REST
    handler / DataMCPTool so all three callers share the same path.
    """
    from aqp.llm.providers.router import router_complete
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_research_papers import ResearchPaperRow
    from aqp.rag import get_default_rag

    with SessionLocal() as session:
        row = session.query(ResearchPaperRow).filter_by(id=paper_id).first()
        if row is None:
            raise ValueError(f"unknown paper {paper_id!r}")
        title = row.title or ""

    rag = get_default_rag()
    hits = rag.query_hybrid(
        query=title,
        corpus="research_papers",
        level="l2",
        k=8,
    )
    excerpts = "\n\n---\n\n".join(h.text for h in hits)
    if not excerpts:
        excerpts = f"(no indexed chunks yet for paper {paper_id})"
    user_prompt = (
        f"Paper title: {title}\n\nExcerpts:\n{excerpts}\n\n"
        "Emit the rationale + YAML now."
    )
    response = router_complete(
        messages=[
            {"role": "system", "content": _SYNTH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format="text",
        temperature=0.3,
    )
    content = response.get("content", "") if isinstance(response, dict) else str(response)
    rationale: str = ""
    yaml_text: str = content
    if "```" in content:
        parts = content.split("```")
        if len(parts) >= 3:
            rationale = parts[0].strip()
            fenced = parts[1]
            if fenced.startswith("yaml"):
                fenced = fenced[4:]
            yaml_text = fenced.strip()
    return {
        "paper_id": paper_id,
        "yaml": yaml_text,
        "rationale": rationale or None,
    }


@celery_app.task(bind=True, name="aqp.tasks.research_paper_tasks.synthesize_strategy_from_paper")
def synthesize_strategy_from_paper(self, *, paper_id: str) -> dict[str, Any]:
    """LLM-drafted strategy YAML grounded in the paper's chunks."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Synthesising strategy for paper {paper_id}")
    try:
        emit(task_id, "calling_llm", "Calling router_complete for synthesis")
        result = synthesize_strategy_impl(paper_id)
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("synthesize_strategy_from_paper failed")
        emit_error(task_id, str(exc))
        raise
