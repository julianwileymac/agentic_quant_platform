"""``backtest_summaries`` RAG corpus — compact backtest result memory.

Indexes the canonical ``backtest_runs`` table into the L0 alpha base.
Each backtest run produces one short indexable paragraph carrying:

- The strategy name (or strategy id when name is unavailable).
- The engine alias (event-driven / vbt-pro:orders / lob / etc.).
- The performance triple (Sharpe / IR / max-drawdown / total return /
  turnover).
- The window dates so the Alpha Researcher agent can compare
  apples-to-apples runs.

The agent reads this corpus to characterise which factor families
have already been explored — avoids re-running the same hypothesis.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def render_backtest_summary_text(payload: dict[str, Any]) -> str:
    """Render one backtest-result row into one indexable paragraph."""
    name = payload.get("strategy_name") or payload.get("strategy_id") or "?"
    engine = payload.get("engine") or "unknown_engine"
    sharpe = payload.get("sharpe")
    mdd = payload.get("max_drawdown")
    ret = payload.get("total_return")
    turnover = payload.get("turnover")
    start = payload.get("start_date")
    end = payload.get("end_date")

    def _fmt(value: Any) -> str:
        if isinstance(value, (int, float)):
            return f"{value:.4f}"
        if value is None:
            return "n/a"
        return str(value)

    parts = [
        f"Backtest of strategy {name} on engine {engine}.",
        f"Window: {start} -> {end}." if start or end else "",
        (
            f"Performance: sharpe={_fmt(sharpe)} max_drawdown={_fmt(mdd)} "
            f"total_return={_fmt(ret)} turnover={_fmt(turnover)}."
        ),
    ]
    summary = payload.get("summary") or {}
    if isinstance(summary, dict):
        extras = [
            f"{k}={_fmt(v)}"
            for k, v in summary.items()
            if k not in {"sharpe", "max_drawdown", "total_return", "turnover"}
            and isinstance(v, (int, float, str))
        ][:6]
        if extras:
            parts.append("Extra metrics: " + ", ".join(extras) + ".")
    experiment_id = payload.get("experiment_id")
    if experiment_id:
        parts.append(f"Umbrella experiment_id={experiment_id}.")
    return "\n".join(p for p in parts if p)


def index_backtest_summaries(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
    since_days: int | None = 365,
) -> int:
    """Walk recent ``backtest_runs`` rows and index them at L0."""
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import BacktestRun
    except Exception:
        logger.info("BacktestRun ORM not available; skipping backtest_summaries index.")
        return 0

    cutoff = (
        datetime.utcnow() - timedelta(days=since_days) if since_days else None
    )
    items: list[tuple[Chunk, dict[str, Any]]] = []
    try:
        with SessionLocal() as session:
            query = session.query(BacktestRun)
            if cutoff is not None and hasattr(BacktestRun, "created_at"):
                query = query.filter(BacktestRun.created_at >= cutoff)
            if limit:
                query = query.limit(limit)
            for row in query.all():
                payload: dict[str, Any] = {
                    "id": getattr(row, "id", None),
                    "strategy_id": getattr(row, "strategy_id", None),
                    "engine": getattr(row, "engine", None),
                    "sharpe": getattr(row, "sharpe", None),
                    "max_drawdown": getattr(row, "max_drawdown", None),
                    "total_return": getattr(row, "total_return", None),
                    "turnover": (getattr(row, "summary", {}) or {}).get("turnover"),
                    "start_date": _iso(getattr(row, "start_date", None)),
                    "end_date": _iso(getattr(row, "end_date", None)),
                    "summary": dict(getattr(row, "summary", {}) or {}),
                    "experiment_id": getattr(row, "experiment_id", None),
                }
                text = render_backtest_summary_text(payload)
                if not text:
                    continue
                meta = {
                    "doc_id": str(payload.get("id")),
                    "source_id": str(payload.get("id")),
                    "engine": str(payload.get("engine") or ""),
                    "sharpe": str(payload.get("sharpe") or ""),
                    "experiment_id": str(payload.get("experiment_id") or ""),
                }
                items.append(
                    (Chunk(text=text, index=0, token_count=len(text.split())), meta)
                )
    except Exception:
        logger.exception("Failed to read backtest_runs.")
        return 0
    return rag.index_chunks("backtest_summaries", items, level="l0")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


__all__ = ["index_backtest_summaries", "render_backtest_summary_text"]
