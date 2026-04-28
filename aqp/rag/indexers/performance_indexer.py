"""Index ``backtest_runs`` performance summaries at L1 ``performance``."""
from __future__ import annotations

import logging

from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def _render_run(run) -> str:
    pieces = [
        f"Backtest {run.id}",
        f"strategy={getattr(run, 'strategy_id', None) or '?'}",
        f"period={getattr(run, 'start', None)} .. {getattr(run, 'end', None)}",
        f"final_equity={getattr(run, 'final_equity', None)}",
        f"sharpe={getattr(run, 'sharpe', None)}",
        f"sortino={getattr(run, 'sortino', None)}",
        f"max_drawdown={getattr(run, 'max_drawdown', None)}",
        f"total_return={getattr(run, 'total_return', None)}",
    ]
    metrics = getattr(run, "metrics", None) or {}
    if isinstance(metrics, dict) and metrics:
        for k, v in list(metrics.items())[:8]:
            pieces.append(f"{k}={v}")
    return ". ".join(str(p) for p in pieces if p)


def index_performance(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 2000,
) -> int:
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import BacktestRun
    except Exception:  # pragma: no cover
        logger.info("BacktestRun ORM not available; skipping performance index.")
        return 0
    items: list[tuple[Chunk, dict]] = []
    try:
        with SessionLocal() as session:
            q = session.query(BacktestRun).order_by(BacktestRun.created_at.desc())
            if limit:
                q = q.limit(limit)
            for row in q.all():
                text = _render_run(row)
                if not text:
                    continue
                items.append(
                    (
                        Chunk(text=text, index=0, token_count=len(text.split())),
                        {
                            "doc_id": f"backtest:{row.id}",
                            "vt_symbol": "",
                            "as_of": str(getattr(row, "completed_at", "") or ""),
                            "source_id": str(row.id),
                        },
                    )
                )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read backtest runs for performance index.")
        return 0
    return rag.index_chunks("performance", items, level="l1")


__all__ = ["index_performance"]
