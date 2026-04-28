"""TradingAgents-style deferred outcome reflector.

For every recent ``agent_decisions`` row that doesn't yet have a
resolved outcome, this module:

1. Computes the realised outcome (raw return + benchmark excess) over
   the configured reflection window.
2. Persists the outcome row in ``memory_outcomes``.
3. Calls the LLM-judge through the quick-tier ``router_complete`` to
   write a short reflection ("we should have ...").
4. Stores the reflection in ``memory_reflections`` AND re-indexes the
   decision into the L0 RAG ``decisions`` corpus so future agent runs
   pick it up via ``HierarchicalRAG``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


_REFLECTION_SYSTEM = (
    "You are a trading reflector. Given a past decision and its realised outcome, "
    "write a 2-4 sentence reflection that future agents can learn from. Be specific "
    "about what was right or wrong. Respond as JSON: "
    '{"lesson": "...", "score": 0..10, "tags": ["..."]}'
)


def run_reflection_pass(
    *,
    lookback_hours: int = 24,
    reflection_window_days: int = 5,
    benchmark_symbol: str = "SPY.NYSE",
    max_decisions: int = 50,
) -> dict[str, Any]:
    """Resolve outcomes + write reflections for recent decisions."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import AgentDecision  # type: ignore[attr-defined]
        from aqp.persistence.models_memory import MemoryOutcome, MemoryReflection
    except Exception:  # pragma: no cover
        return {"resolved": 0, "reflected": 0, "error": "ORM unavailable"}

    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
    resolved = 0
    reflected = 0
    with SessionLocal() as session:
        decisions = (
            session.query(AgentDecision)
            .filter(AgentDecision.as_of <= cutoff)
            .order_by(AgentDecision.as_of.desc())
            .limit(max_decisions)
            .all()
        )
        for d in decisions:
            decision_id = str(getattr(d, "id", "") or "")
            vt_symbol = str(getattr(d, "vt_symbol", "") or "")
            if not vt_symbol or not decision_id:
                continue
            existing = (
                session.query(MemoryOutcome)
                .filter(MemoryOutcome.decision_id == decision_id)
                .one_or_none()
            )
            if existing is not None:
                continue
            outcome = _compute_outcome(
                vt_symbol,
                getattr(d, "as_of", None),
                window_days=reflection_window_days,
                benchmark=benchmark_symbol,
            )
            if outcome is None:
                continue
            session.add(
                MemoryOutcome(
                    decision_id=decision_id,
                    vt_symbol=vt_symbol,
                    decision_at=getattr(d, "as_of", None),
                    outcome_at=outcome["outcome_at"],
                    raw_return=outcome["raw_return"],
                    benchmark_return=outcome["benchmark_return"],
                    excess_return=outcome["excess_return"],
                    direction_correct=outcome["direction_correct"],
                    meta=outcome.get("meta", {}),
                )
            )
            resolved += 1
            lesson = _write_reflection(d, outcome)
            session.add(
                MemoryReflection(
                    role=getattr(d, "role", "trader"),
                    run_id=str(getattr(d, "agent_run_id", "") or ""),
                    vt_symbol=vt_symbol,
                    as_of=outcome["outcome_at"],
                    lesson=lesson["lesson"],
                    outcome=outcome["excess_return"],
                    meta={"score": lesson.get("score"), "tags": lesson.get("tags", [])},
                )
            )
            reflected += 1
            try:
                from aqp.rag.indexers.decisions_indexer import index_decision_payloads

                index_decision_payloads(
                    [
                        {
                            "id": decision_id,
                            "vt_symbol": vt_symbol,
                            "as_of": str(outcome["outcome_at"]),
                            "text": (
                                f"Decision {decision_id} for {vt_symbol}. "
                                f"Reflection: {lesson['lesson']} "
                                f"Outcome: raw={outcome['raw_return']:.4f} "
                                f"excess={outcome['excess_return']:.4f}"
                            ),
                        }
                    ]
                )
            except Exception:  # noqa: BLE001
                logger.debug("RAG re-index failed for %s", decision_id, exc_info=True)
        session.commit()
    return {"resolved": resolved, "reflected": reflected}


def _compute_outcome(
    vt_symbol: str,
    as_of: datetime | None,
    *,
    window_days: int,
    benchmark: str,
) -> dict[str, Any] | None:
    try:
        from aqp.data.bars import get_bars
    except Exception:  # pragma: no cover
        return None
    try:
        df = get_bars(vt_symbol, lookback_days=window_days * 4)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    if as_of is None:
        return None
    closes = df.copy()
    if "timestamp" in closes.columns:
        closes = closes.sort_values("timestamp")
        try:
            future = closes[closes["timestamp"] >= as_of].head(window_days + 1)
        except Exception:
            future = closes.tail(window_days + 1)
    else:
        future = closes.tail(window_days + 1)
    if len(future) < 2:
        return None
    first_close = float(future["close"].iloc[0])
    last_close = float(future["close"].iloc[-1])
    raw_return = (last_close / first_close - 1.0) if first_close else 0.0
    bench_return = 0.0
    try:
        bdf = get_bars(benchmark, lookback_days=window_days * 4)
        if bdf is not None and not bdf.empty and "close" in bdf.columns:
            bdf = bdf.tail(window_days + 1)
            if len(bdf) >= 2:
                bench_return = float(bdf["close"].iloc[-1]) / float(bdf["close"].iloc[0]) - 1.0
    except Exception:  # noqa: BLE001
        pass
    return {
        "outcome_at": future["timestamp"].iloc[-1] if "timestamp" in future.columns else datetime.utcnow(),
        "raw_return": raw_return,
        "benchmark_return": bench_return,
        "excess_return": raw_return - bench_return,
        "direction_correct": 1.0 if raw_return >= 0 else 0.0,
        "meta": {"window_days": window_days, "benchmark": benchmark},
    }


def _write_reflection(decision: Any, outcome: dict[str, Any]) -> dict[str, Any]:
    try:
        from aqp.config import settings
        from aqp.llm.providers.router import router_complete

        prompt = (
            f"Decision: {json.dumps(_decision_to_dict(decision), default=str)}\n\n"
            f"Outcome: {json.dumps({k: outcome[k] for k in ('raw_return', 'benchmark_return', 'excess_return')}, default=str)}"
        )
        res = router_complete(
            provider=settings.llm_provider,
            model=settings.llm_quick_model,
            messages=[
                {"role": "system", "content": _REFLECTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
            tier="quick",
        )
        try:
            return json.loads((res.content or "").strip().strip("`"))
        except Exception:
            return {"lesson": (res.content or "")[:400], "score": None, "tags": []}
    except Exception:  # noqa: BLE001
        excess = outcome.get("excess_return", 0.0)
        verdict = "Decision was correct." if excess >= 0 else "Decision was wrong."
        return {"lesson": f"{verdict} Excess {excess:.4f}.", "score": None, "tags": []}


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in ("id", "vt_symbol", "as_of", "action", "rationale", "summary", "plan", "verdict"):
        if hasattr(decision, col):
            out[col] = getattr(decision, col)
    return out


__all__ = ["run_reflection_pass"]
