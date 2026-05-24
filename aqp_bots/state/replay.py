"""Time-travel debugging by replaying ``bot_events``.

Used by:

- ``aqp-bots replay <slug> --from ts --to ts`` (CLI, Phase 12)
- ``POST /bots/{ref}/replay`` (REST, Phase 12)
- ``BotKernel`` startup recovery (rebuild from snapshot + replay).

The reconstruction is dispatched through the same event-handling
callbacks the live runtime uses so the in-memory state at any
historical point ``T`` matches what the bot saw at ``T``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplayCursor:
    """Bookkeeping for a single replay pass."""

    bot_id: str
    started_at: datetime
    events_seen: int = 0
    final_seq_no: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def replay_events(
    *,
    bot_id: str,
    handlers: dict[str, Callable[[dict[str, Any]], None]],
    since_seq: int = 0,
    until_seq: int | None = None,
    limit: int | None = None,
) -> ReplayCursor:
    """Replay ``bot_events`` between ``since_seq`` and ``until_seq``.

    ``handlers`` maps ``event_type -> callable(event_data)``; events
    whose type isn't in the map are noted on
    :attr:`ReplayCursor.skipped` and not dispatched.

    Returns the :class:`ReplayCursor` with stats.
    """
    cursor = ReplayCursor(bot_id=bot_id, started_at=datetime.utcnow())
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_bots import BotEvent
        from sqlalchemy import select
    except Exception:  # noqa: BLE001
        logger.warning("replay_events: persistence unavailable")
        return cursor

    try:
        with SessionLocal() as session:
            stmt = (
                select(BotEvent)
                .where(BotEvent.bot_id == bot_id, BotEvent.seq_no > since_seq)
                .order_by(BotEvent.seq_no)
            )
            if until_seq is not None:
                stmt = stmt.where(BotEvent.seq_no <= until_seq)
            if limit:
                stmt = stmt.limit(limit)
            for row in session.execute(stmt).scalars():
                cursor.events_seen += 1
                cursor.final_seq_no = int(row.seq_no)
                handler = handlers.get(row.event_type)
                if handler is None:
                    cursor.skipped.append(row.event_type)
                    continue
                try:
                    handler(dict(row.event_data or {}))
                except Exception as exc:  # noqa: BLE001
                    cursor.errors.append(f"{row.event_type}@{row.seq_no}: {exc!r}")
    except Exception:  # noqa: BLE001
        logger.exception("replay_events: query failed")
    return cursor


__all__ = ["ReplayCursor", "replay_events"]
