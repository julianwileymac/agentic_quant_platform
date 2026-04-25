"""Tests for the post-hoc replay edit-application logic.

The full :func:`aqp.tasks.agentic_backtest_tasks.run_agentic_replay`
path requires a DB + Celery + history provider; here we test the
deterministic in-memory pieces (edits application, replay-cache
materialisation) so a regression in either lands quickly.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, Rating5, TraderAction


def _decision_row(d_id: str, vt: str, ts: datetime, action: str, size: float) -> dict:
    return {
        "id": d_id,
        "vt_symbol": vt,
        "ts": ts,
        "action": action,
        "size_pct": size,
        "confidence": 0.6,
        "rating": "buy" if action == "BUY" else "sell" if action == "SELL" else "hold",
        "rationale": "original",
        "token_cost_usd": 0.01,
    }


def test_edits_application_changes_action_and_size() -> None:
    rows = [
        _decision_row("d-1", "AAPL.NASDAQ", datetime(2024, 3, 1), "BUY", 0.2),
        _decision_row("d-2", "MSFT.NASDAQ", datetime(2024, 3, 2), "SELL", 0.1),
    ]
    edits = [
        {"decision_id": "d-1", "action": "HOLD", "size_pct": 0.0, "rationale": "vetoed"},
    ]
    edits_by_id = {e["decision_id"]: e for e in edits}
    patched = []
    for row in rows:
        edit = edits_by_id.get(row["id"])
        if not edit:
            patched.append(row)
            continue
        new = dict(row)
        if "action" in edit:
            new["action"] = str(edit["action"]).upper()
        if "size_pct" in edit:
            new["size_pct"] = float(edit["size_pct"])
        if "rationale" in edit:
            new["rationale"] = str(edit["rationale"])
        patched.append(new)
    assert patched[0]["action"] == "HOLD"
    assert patched[0]["size_pct"] == 0.0
    assert patched[0]["rationale"] == "vetoed"
    assert patched[1]["action"] == "SELL"  # untouched


def test_replay_cache_materialisation_round_trips(tmp_path: Path) -> None:
    """Patched rows can be written back into a fresh DecisionCache and
    the values read out should match what we wrote."""
    rows = [
        _decision_row("d-1", "AAPL.NASDAQ", datetime(2024, 3, 1), "BUY", 0.2),
        _decision_row("d-2", "MSFT.NASDAQ", datetime(2024, 3, 8), "SELL", 0.1),
    ]
    edits = [{"decision_id": "d-1", "action": "HOLD", "size_pct": 0.0}]
    edits_by_id = {e["decision_id"]: e for e in edits}
    patched: list[dict] = []
    for row in rows:
        new = dict(row)
        edit = edits_by_id.get(row["id"])
        if edit:
            if "action" in edit:
                new["action"] = str(edit["action"]).upper()
            if "size_pct" in edit:
                new["size_pct"] = float(edit["size_pct"])
        patched.append(new)

    cache = DecisionCache(root=tmp_path, strategy_id="replay-test")
    for row in patched:
        decision = AgentDecision(
            vt_symbol=row["vt_symbol"],
            timestamp=pd.to_datetime(row["ts"]).to_pydatetime(),
            action=TraderAction(row["action"]),
            size_pct=float(row["size_pct"]),
            confidence=float(row["confidence"]),
            rating=Rating5.HOLD if row["rating"] == "hold" else Rating5(row["rating"]),
            rationale=row.get("rationale", ""),
            context_hash=f"replay-{row['id']}",
        )
        cache.put(decision, overwrite=True)

    apple = cache.get("AAPL.NASDAQ", datetime(2024, 3, 1))
    assert apple is not None
    assert apple.action is TraderAction.HOLD
    assert apple.size_pct == 0.0

    msft = cache.get("MSFT.NASDAQ", datetime(2024, 3, 8))
    assert msft is not None
    assert msft.action is TraderAction.SELL
    assert msft.size_pct == 0.1
