"""Pydantic models shared across the strategy ABC, client, and MCP tools."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Decision(BaseModel):
    """Outcome of a single :meth:`IngestionRateLimitStrategy.check` call."""

    allow: bool
    remaining: float
    capacity: float
    refill_rate: float = Field(description="Tokens per second")
    retry_after_ms: int = 0
    service: str = ""
    key_id: str = ""
    user_id: str = ""
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReserveOutcome(BaseModel):
    """Outcome of a multi-token preflight :meth:`reserve`."""

    allow: bool
    reservation_id: str | None = None
    requested: int
    remaining: float
    capacity: float
    ttl_s: int
    expires_at: datetime | None = None
    service: str = ""
    key_id: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyDescriptor(BaseModel):
    """Lightweight projection of a ``rl_policies`` row used by the MCP tools.

    Secret fields (vault paths, vendor IDs) are deliberately omitted.
    """

    policy_id: str
    service: str
    tier: str
    capacity: int
    refill_rate: float = Field(description="Tokens per second")
    refill_interval_ms: int
    window_ms: int
    notes: str | None = None


class KeyDescriptor(BaseModel):
    """Projection of a ``rl_keys`` row safe for the operator UI.

    The ``vault_path`` is NEVER returned to the client — the raw
    vendor secret remains in Vault. Only the metadata that lets the
    operator identify and rotate the key is exposed.
    """

    key_id: str
    user_id: str
    team_id: str | None = None
    service: str
    policy_id: str
    label: str
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class LedgerEntry(BaseModel):
    """One row in ``rl_ledger`` — audit + observability surface."""

    ts: datetime
    user_id: str
    service: str
    key_id: str
    tokens_consumed: int
    decision: str = Field(description="allow | deny | cached")
    request_hash: bytes | None = None
    asset_key: str | None = None
    actor_kind: str = Field(default="user", description="user | agent | service")
    agent_subject: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Decision",
    "KeyDescriptor",
    "LedgerEntry",
    "PolicyDescriptor",
    "ReserveOutcome",
]
