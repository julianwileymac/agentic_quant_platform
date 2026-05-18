"""``rl_trajectory_summaries`` RAG corpus — compact RL-run summary memory.

Indexes the canonical ``rl_runs`` table into the L0 alpha base. The
:class:`aqp.agents.quant.StrategyExecutor` agent reads this corpus
to compare across RL experiment iterations and pick the best
deployment candidate.

Each run produces one short indexable paragraph carrying:

- The spec slug + the run target (train / evaluate / paper /
  replay / walk_forward).
- The performance triple (final equity, max-drawdown, Sharpe).
- The truncation rate (FinRL-X "stop properly" diagnostic, when
  available on ``result_summary``).
- The advantage-estimator name (when configured via
  ``spec.training.advantage``).
- The MLflow run id + checkpoint path for replay.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from aqp.metadata import make_urn
from aqp.rag.chunker import Chunk
from aqp.rag.document_aspects import (
    DocumentEmissionPayload,
    emit_documents_batch,
    extract_glossary_terms,
)
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)
_INSTRUMENT_ID_SANITIZER = re.compile(r"[^A-Za-z0-9._:-]+")


def _instrument_urn_from_metadata(meta: dict[str, Any]) -> str | None:
    for key in ("vt_symbol", "ticker", "cusip", "cik"):
        raw_value = str(meta.get(key) or "").strip()
        if not raw_value:
            continue
        urn_id = _INSTRUMENT_ID_SANITIZER.sub("-", raw_value).strip("-.:")
        if urn_id:
            return make_urn("instrument", "prod", urn_id)
    return None


def _emit_document_aspects(items: list[tuple[Chunk, dict[str, Any]]]) -> None:
    if not items:
        return
    payloads: list[DocumentEmissionPayload] = []
    for chunk, meta in items:
        payloads.append(
            {
                "document_id": str(meta.get("source_id") or meta.get("doc_id") or ""),
                "content_text": chunk.text,
                "instrument_urn": _instrument_urn_from_metadata(meta),
                "valid_from": meta.get("valid_from"),
                "glossary_terms": extract_glossary_terms(chunk.text),
            }
        )
    try:
        emitted = emit_documents_batch(payloads)
        logger.info("Emitted %d RL-summary Document aspects.", len(emitted))
    except Exception:
        logger.exception(
            "Document-aspect emission failed for rl_trajectory_summaries; continuing index run."
        )


def render_rl_run_summary_text(payload: dict[str, Any]) -> str:
    """Render one ``rl_runs`` row into one indexable paragraph."""
    spec = payload.get("spec_slug") or payload.get("spec_id") or "?"
    target = payload.get("target") or "?"
    status = payload.get("status") or "?"

    def _fmt(value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value:.4f}"
        if value is None:
            return "n/a"
        return str(value)

    parts = [
        f"RL run spec={spec} target={target} status={status}.",
        (
            f"Final equity={_fmt(payload.get('final_value'))} "
            f"sharpe={_fmt(payload.get('sharpe'))} "
            f"max_drawdown={_fmt(payload.get('max_drawdown'))} "
            f"total_return={_fmt(payload.get('total_return'))} "
            f"mean_reward={_fmt(payload.get('mean_reward'))}."
        ),
    ]
    summary = payload.get("result_summary") or {}
    if isinstance(summary, dict):
        if "truncation_rate" in summary:
            parts.append(
                f"FinRL-X truncation_rate={_fmt(summary.get('truncation_rate'))}."
            )
        if "stop_properly_coef" in summary:
            parts.append(
                f"stop_properly_penalty_coef={_fmt(summary.get('stop_properly_coef'))}."
            )
        if "advantage_estimator" in summary:
            parts.append(f"Advantage estimator: {summary.get('advantage_estimator')}.")
    if payload.get("mlflow_run_id"):
        parts.append(f"mlflow_run_id={payload['mlflow_run_id']}.")
    if payload.get("checkpoint"):
        parts.append(f"checkpoint={payload['checkpoint']}.")
    return "\n".join(p for p in parts if p)


def index_rl_trajectory_summaries(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
    since_days: int | None = 365,
) -> int:
    """Walk recent ``rl_runs`` rows and index them at L0."""
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import RLRun, RLExperimentSpec as RLSpecRow
    except Exception:
        logger.info("RL ORM not available; skipping rl_trajectory_summaries index.")
        return 0

    cutoff = (
        datetime.utcnow() - timedelta(days=since_days) if since_days else None
    )
    items: list[tuple[Chunk, dict[str, Any]]] = []
    try:
        with SessionLocal() as session:
            # Resolve spec slugs in one pass so the rendered text is human-readable.
            spec_id_to_slug: dict[str, str] = {
                row.id: row.slug for row in session.query(RLSpecRow).all()
            }
            query = session.query(RLRun)
            if cutoff is not None:
                query = query.filter(RLRun.started_at >= cutoff)
            if limit:
                query = query.limit(limit)
            for row in query.all():
                payload: dict[str, Any] = {
                    "id": row.id,
                    "spec_id": row.spec_id,
                    "spec_slug": spec_id_to_slug.get(row.spec_id),
                    "target": row.target,
                    "status": row.status,
                    "mean_reward": row.mean_reward,
                    "sharpe": row.sharpe,
                    "max_drawdown": row.max_drawdown,
                    "final_value": row.final_value,
                    "total_return": row.total_return,
                    "mlflow_run_id": row.mlflow_run_id,
                    "checkpoint": row.checkpoint,
                    "result_summary": dict(row.result_summary or {}),
                    "experiment_id": getattr(row, "experiment_id", None),
                }
                text = render_rl_run_summary_text(payload)
                if not text:
                    continue
                meta = {
                    "doc_id": str(row.id),
                    "source_id": str(row.id),
                    "spec_slug": str(payload.get("spec_slug") or ""),
                    "target": str(payload.get("target") or ""),
                    "experiment_id": str(payload.get("experiment_id") or ""),
                    "valid_from": str(getattr(row, "started_at", "") or ""),
                }
                items.append(
                    (Chunk(text=text, index=0, token_count=len(text.split())), meta)
                )
    except Exception:
        logger.exception("Failed to read rl_runs.")
        return 0
    _emit_document_aspects(items)
    return rag.index_chunks("rl_trajectory_summaries", items, level="l0")


__all__ = ["index_rl_trajectory_summaries", "render_rl_run_summary_text"]
