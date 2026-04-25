"""Celery task that runs :class:`EquityReportPipeline` and persists the result."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aqp.tasks.equity_report_tasks.run_equity_report",
)
def run_equity_report(
    self,
    *,
    vt_symbol: str,
    as_of: str,
    peers: list[str] | None = None,
    sections: list[str] | None = None,
    valuation_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the section pipeline and persist a :class:`EquityReport` row."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Running equity report for {vt_symbol}")
    try:
        from aqp.agents.financial.equity_pipeline import EquityReportPipeline
        from aqp.persistence.db import get_session
        from aqp.persistence.models import EquityReport as EquityReportRow

        # Pull shared snapshots from existing tools.
        as_of_dt = datetime.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        as_of_iso = as_of_dt.isoformat()

        fundamentals: dict[str, Any] = {}
        peer_fundamentals: dict[str, Any] = {}
        try:
            from aqp.agents.tools.fundamentals_tool import compute_fundamentals_snapshot

            fundamentals = compute_fundamentals_snapshot(vt_symbol, as_of_iso) or {}
            for peer in peers or []:
                peer_fundamentals[peer] = (
                    compute_fundamentals_snapshot(peer, as_of_iso) or {}
                )
        except Exception:
            logger.info("equity report: fundamentals snapshot unavailable", exc_info=True)

        news_digest: list[dict[str, Any]] = []
        try:
            from aqp.agents.tools.news_tool import fetch_news_items

            news_digest = fetch_news_items(vt_symbol, as_of=as_of_iso, lookback_days=30) or []
        except Exception:
            logger.info("equity report: news digest unavailable", exc_info=True)

        price_summary: dict[str, Any] = {}
        try:
            from aqp.agents.tools.technical_tool import compute_technical_snapshot

            price_summary = compute_technical_snapshot(
                vt_symbol, as_of=as_of_iso, lookback_days=120
            ) or {}
        except Exception:
            logger.info("equity report: technical snapshot unavailable", exc_info=True)

        emit(task_id, "running", "Running section agents…")
        pipeline = EquityReportPipeline(sections=sections or None)
        report = pipeline.run(
            vt_symbol=vt_symbol,
            as_of=as_of_dt,
            price_summary=price_summary,
            fundamentals=fundamentals,
            news_digest=news_digest,
            peers=peers or [],
            peer_fundamentals=peer_fundamentals,
            valuation_inputs=valuation_inputs,
        )

        with get_session() as session:
            row = EquityReportRow(
                vt_symbol=vt_symbol,
                as_of=as_of_dt,
                peers=list(peers or []),
                sections=report.sections,
                usage=report.usage,
                valuation=report.valuation,
                catalysts=report.catalysts,
                sensitivity=report.sensitivity,
                cost_usd=float(report.cost_usd or 0.0),
                status="completed",
            )
            session.add(row)
            session.flush()
            row_id = row.id

        payload = {
            "id": row_id,
            "vt_symbol": vt_symbol,
            "as_of": as_of_iso,
            "n_sections": len(report.sections),
            "cost_usd": float(report.cost_usd or 0.0),
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_equity_report failed")
        emit_error(task_id, str(exc))
        raise
