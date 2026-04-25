"""Paper trading session state snapshot — for crash recovery and dashboards."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PaperSessionState:
    """A snapshot periodically flushed to Postgres.

    Reconstruction on restart is best-effort: replaying the full ledger is
    authoritative, but the state snapshot lets the UI show an approximate
    current view when the worker was killed mid-session.
    """

    run_id: str
    task_id: str | None
    run_name: str
    strategy_id: str
    brokerage: str
    feed: str
    started_at: datetime
    last_heartbeat_at: datetime
    bars_seen: int = 0
    orders_submitted: int = 0
    fills: int = 0
    cash: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_error: str | None = None
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        d["last_heartbeat_at"] = self.last_heartbeat_at.isoformat()
        return d
