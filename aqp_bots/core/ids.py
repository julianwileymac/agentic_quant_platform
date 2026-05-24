"""Identifier types + UUIDv7 generators.

UUIDv7 (RFC 9562 §5.7) embeds a 48-bit Unix-millisecond timestamp in
the high bits so generated ids are time-ordered.  We use them for:

- ``client_order_id`` — the canonical idempotency key for new-order
  requests (blueprint §G.4).
- ``event seq_no`` — the monotonic sequence we attach to event-sourced
  ``bot_events`` rows (Phase 4).

Falls back to UUIDv4 when the optional :mod:`uuid_utils` package is not
installed; the time-ordering property is best-effort and consumers must
not rely on it for cross-process global ordering.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import NewType

try:
    import uuid_utils  # type: ignore[import-untyped]

    _HAS_UUID7 = True
except Exception:  # noqa: BLE001
    _HAS_UUID7 = False


# Newtype aliases — keep them ``str`` at runtime so downstream JSON
# serialisation Just Works, but the type checker enforces correctness.
BotID = NewType("BotID", str)
StrategyID = NewType("StrategyID", str)
RunID = NewType("RunID", str)
OrderID = NewType("OrderID", str)


def _new_uuid_str() -> str:
    if _HAS_UUID7:
        return str(uuid_utils.uuid7())  # type: ignore[attr-defined]
    return str(uuid.uuid4())


def new_bot_id() -> BotID:
    """Generate a new bot id (UUIDv7 if available, else v4)."""
    return BotID(f"bot-{_new_uuid_str()}")


def new_strategy_id(name: str = "") -> StrategyID:
    """Generate a new strategy id, optionally namespaced by ``name``."""
    if name:
        return StrategyID(f"strat-{name}-{_new_uuid_str()}")
    return StrategyID(f"strat-{_new_uuid_str()}")


def new_run_id() -> RunID:
    """Generate a new run id."""
    return RunID(f"run-{_new_uuid_str()}")


def new_client_order_id(
    *,
    bot_id: str = "",
    content: bytes | None = None,
) -> OrderID:
    """Generate a deterministic-prefix client_order_id.

    Format: ``coid-{uuidv7}-{content_hash[:8]}``

    The content hash is the first 8 hex chars of SHA256(content) and lets
    the idempotency LRU dedup retries of the same logical order (e.g.
    the strategy fires the same buy twice because of a websocket
    reconnect). When ``content`` is None only the UUID is used.
    """
    uid = _new_uuid_str()
    if content is not None:
        digest = hashlib.sha256(content).hexdigest()[:8]
        return OrderID(f"coid-{uid}-{digest}")
    return OrderID(f"coid-{uid}")


__all__ = [
    "BotID",
    "OrderID",
    "RunID",
    "StrategyID",
    "new_bot_id",
    "new_client_order_id",
    "new_run_id",
    "new_strategy_id",
]
