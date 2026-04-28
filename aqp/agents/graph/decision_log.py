"""Append-only decision log + deferred outcome resolution.

Mirrors TradingAgents' ``utils/memory.py`` decision log: every
:class:`AgentRunV2` that produced a ``trader_signal`` or
``portfolio_decision`` writes one pending entry; a later resolver pass
fills in the realised outcome and triggers a reflection.

Two writers:

- :func:`append_pending_decision` — called at the end of a graph run.
- :func:`resolve_pending_decisions` — Celery-friendly batch resolver
  that delegates the heavy lift to
  :func:`aqp.agents.analysis.reflector.run_reflection_pass`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def _ensure_path() -> Path:
    p = Path(settings.agent_decision_log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_pending_decision(
    *,
    run_id: str,
    spec_name: str,
    vt_symbol: str,
    as_of: str | datetime,
    decision: dict[str, Any],
) -> None:
    """Append one pending decision entry to the markdown log."""
    path = _ensure_path()
    record = {
        "run_id": run_id,
        "spec_name": spec_name,
        "vt_symbol": vt_symbol,
        "as_of": as_of.isoformat() if isinstance(as_of, datetime) else str(as_of),
        "decision": decision,
        "status": "pending",
        "logged_at": datetime.utcnow().isoformat(),
    }
    line = "<!--AQP_DECISION " + json.dumps(record, default=str) + "-->"
    md = (
        f"\n## Decision {run_id} — {spec_name} — {vt_symbol} @ {record['as_of']}\n\n"
        f"```json\n{json.dumps(decision, default=str, indent=2)}\n```\n\n"
        f"{line}\n"
    )
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(md)
    except Exception:  # pragma: no cover
        logger.debug("decision log append failed", exc_info=True)


def resolve_pending_decisions(**kwargs: Any) -> dict[str, Any]:
    """Drive a single reflection pass."""
    try:
        from aqp.agents.analysis.reflector import run_reflection_pass

        return run_reflection_pass(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("resolve_pending_decisions failed")
        return {"error": str(exc)}


def read_recent_entries(limit: int = 25) -> list[str]:
    """Return the last ``limit`` decision sections from the markdown log."""
    path = Path(settings.agent_decision_log_path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover
        return []
    sections = text.split("\n## Decision ")
    return [f"## Decision {s}" for s in sections[-limit:] if s.strip()]


__all__ = [
    "append_pending_decision",
    "read_recent_entries",
    "resolve_pending_decisions",
]
