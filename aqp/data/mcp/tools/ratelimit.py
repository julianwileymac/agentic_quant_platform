"""``data.ratelimit.*`` DataMCP tools (Phase 0 — Foundations, plan section 4).

Four tools that let agents and operators inspect, reserve, list, and
update rate-limit state through the canonical DataMCP boundary
(AGENTS rule 22). Mutating tools set ``mutates=True`` so the matching
HTTP path attaches ``Depends(require_step_up(max_age_seconds=180))``
per AGENTS rule 52.

- ``data.ratelimit.status`` (read) — per-key bucket snapshot.
- ``data.ratelimit.reserve`` (mutating, step-up) — preflight reserve
  for partitioned backfills.
- ``data.ratelimit.policy.list`` (read) — enumerate policies for the
  EntityPicker dropdown.
- ``data.ratelimit.policy.update`` (mutating, Tier-P only,
  step-up) — change capacity / refill_rate on an existing policy.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client():
    from aqp_ratelimit import get_ratelimit_client

    return get_ratelimit_client()


def _resolve_user_id(ctx: MCPToolContext) -> str:
    if ctx.actor_kind == "user" and ctx.actor:
        return str(ctx.actor)
    # For agent calls, the agent_subject is recorded on ctx.extras
    # (set by the new ingest plane); the per-user bucket still uses
    # the on-behalf-of human's id from the delegated token's ``sub``.
    extras = ctx.extras or {}
    on_behalf = extras.get("on_behalf_of_user_id")
    if on_behalf:
        return str(on_behalf)
    return str(ctx.actor or "anonymous")


# ---------------------------------------------------------------------------
# Tool 1: status (read)
# ---------------------------------------------------------------------------


class StatusInput(BaseModel):
    service: str | None = Field(
        default=None,
        description="Filter to a single service (e.g. polygon.aggregates).",
    )
    key_id: str | None = Field(
        default=None,
        description="Filter to a single key (label or UUID).",
    )


@register_data_mcp_tool
class RateLimitStatusTool(DataMCPTool):
    """Per-(user, service, key_id) bucket snapshot."""

    name = "data.ratelimit.status"
    description = (
        "Return the current bucket state (remaining / capacity / refill_rate / "
        "retry_after_ms) for the calling user. With no filters, returns every "
        "(service, key_id) the user has buckets for."
    )
    args_schema = StatusInput
    category = "ratelimit"
    tags = ("ratelimit", "credentials", "quota")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        service: str | None = None,
        key_id: str | None = None,
    ) -> MCPToolResult:
        from sqlalchemy import and_

        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import RateLimitKey

        user_id = _resolve_user_id(ctx)
        with get_session() as session:
            query = session.query(RateLimitKey).filter(
                RateLimitKey.owner_user_id == user_id,
                RateLimitKey.revoked_at.is_(None),
            )
            if service is not None:
                query = query.filter(RateLimitKey.service == service)
            if key_id is not None:
                query = query.filter(
                    and_(
                        RateLimitKey.label == key_id,
                    )
                )
            keys = query.all()

        client = _get_client()
        out: list[dict[str, Any]] = []
        for row in keys:
            decision = client.status(
                user_id=user_id,
                service=row.service,
                key_id=row.label,
            )
            out.append(
                {
                    "service": row.service,
                    "key_id": row.label,
                    "remaining": decision.remaining,
                    "capacity": decision.capacity,
                    "refill_rate": decision.refill_rate,
                    "allow": decision.allow,
                    "issued_at": row.issued_at.isoformat() if row.issued_at else None,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                }
            )
        return MCPToolResult(
            ok=True,
            data={"buckets": out},
            summary=f"{len(out)} bucket(s) for user",
            rows_returned=len(out),
        )


# ---------------------------------------------------------------------------
# Tool 2: reserve (mutating, step-up)
# ---------------------------------------------------------------------------


class ReserveInput(BaseModel):
    service: str
    key_id: str
    n_tokens: int = Field(ge=1)
    ttl_s: int = Field(default=3600, ge=1, le=86400)


@register_data_mcp_tool
class RateLimitReserveTool(DataMCPTool):
    """Preflight token reservation for partitioned backfills."""

    name = "data.ratelimit.reserve"
    description = (
        "Reserve N tokens up-front for a partitioned backfill. The reservation "
        "auto-releases on TTL expiry. Returns a reservation_id the caller can "
        "explicitly release via the REST surface. Used by the aqp materialize "
        "--partition-range preflight."
    )
    args_schema = ReserveInput
    category = "ratelimit"
    tags = ("ratelimit", "reserve", "backfill")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        service: str,
        key_id: str,
        n_tokens: int,
        ttl_s: int = 3600,
    ) -> MCPToolResult:
        user_id = _resolve_user_id(ctx)
        client = _get_client()
        # Bridge MCP context to per-agent dual-debit (rule 54).
        from aqp_ratelimit.bridges.agent_bridge import build_ratelimit_ctx

        rl_ctx = build_ratelimit_ctx(ctx)
        outcome = client.reserve(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ttl_s=ttl_s,
            ctx=rl_ctx,
        )
        return MCPToolResult(
            ok=outcome.allow,
            data={
                "allow": outcome.allow,
                "reservation_id": outcome.reservation_id,
                "requested": outcome.requested,
                "remaining": outcome.remaining,
                "capacity": outcome.capacity,
                "ttl_s": outcome.ttl_s,
            },
            summary=(
                f"reserved {n_tokens} tokens"
                if outcome.allow
                else (
                    f"reservation rejected; needed {n_tokens}, "
                    f"have {outcome.remaining:.1f}"
                )
            ),
            error=(
                None
                if outcome.allow
                else (
                    f"would need {n_tokens} tokens but only {outcome.remaining:.1f} "
                    "remaining"
                )
            ),
        )


# ---------------------------------------------------------------------------
# Tool 3: policy.list (read)
# ---------------------------------------------------------------------------


class PolicyListInput(BaseModel):
    service: str | None = None
    tier: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class RateLimitPolicyListTool(DataMCPTool):
    """Enumerate active rate-limit policies."""

    name = "data.ratelimit.policy.list"
    description = (
        "Enumerate active (service, tier) rate-limit policies the calling "
        "workspace can see. Returns capacity, refill_rate, and notes — never "
        "vault paths or vendor secrets."
    )
    args_schema = PolicyListInput
    category = "ratelimit"
    tags = ("ratelimit", "policy")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        service: str | None = None,
        tier: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import RateLimitPolicy

        with get_session() as session:
            query = session.query(RateLimitPolicy).filter(
                RateLimitPolicy.is_active.is_(True)
            )
            if service is not None:
                query = query.filter(RateLimitPolicy.service == service)
            if tier is not None:
                query = query.filter(RateLimitPolicy.tier == tier)
            rows = query.order_by(RateLimitPolicy.service.asc()).limit(int(limit)).all()
        out = [
            {
                "policy_id": row.id,
                "service": row.service,
                "tier": row.tier,
                "capacity": int(row.capacity),
                "refill_rate": float(row.refill_rate),
                "refill_interval_ms": int(row.refill_interval_ms or 1000),
                "window_ms": int(row.window_ms or 60_000),
                "notes": row.notes,
            }
            for row in rows
        ]
        return MCPToolResult(
            ok=True,
            data={"policies": out},
            summary=f"{len(out)} active policy(ies)",
            rows_returned=len(out),
        )


# ---------------------------------------------------------------------------
# Tool 4: policy.update (mutating, Tier-P only, step-up)
# ---------------------------------------------------------------------------


class PolicyUpdateInput(BaseModel):
    policy_id: str
    capacity: int | None = Field(default=None, ge=1)
    refill_rate: float | None = Field(default=None, gt=0)
    notes: str | None = None
    is_active: bool | None = None


@register_data_mcp_tool
class RateLimitPolicyUpdateTool(DataMCPTool):
    """Tier-P only: change capacity / refill_rate on an existing policy."""

    name = "data.ratelimit.policy.update"
    description = (
        "Update an existing rate-limit policy. Only Platform Engineers can "
        "invoke this; the API path attaches step-up MFA. Changing capacity "
        "or refill_rate takes effect on the next Redis cache refresh "
        "(usually within 60 seconds via the Celery beat task)."
    )
    args_schema = PolicyUpdateInput
    category = "ratelimit"
    tags = ("ratelimit", "policy", "admin")
    mutates = True
    required_scopes = ("data:read", "data:write", "admin:cluster")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        policy_id: str,
        capacity: int | None = None,
        refill_rate: float | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
    ) -> MCPToolResult:
        from datetime import datetime

        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import RateLimitPolicy

        with get_session() as session:
            row = session.get(RateLimitPolicy, policy_id)
            if row is None:
                return MCPToolResult(
                    ok=False,
                    error=f"policy {policy_id!r} not found",
                )
            changed: dict[str, Any] = {}
            if capacity is not None:
                row.capacity = int(capacity)
                changed["capacity"] = int(capacity)
            if refill_rate is not None:
                row.refill_rate = float(refill_rate)
                changed["refill_rate"] = float(refill_rate)
            if notes is not None:
                row.notes = str(notes)
                changed["notes"] = str(notes)
            if is_active is not None:
                row.is_active = bool(is_active)
                changed["is_active"] = bool(is_active)
            row.updated_at = datetime.utcnow()
            session.commit()

            # Invalidate the cache so the next status / check sees the new policy.
            try:
                from aqp.cache.invalidation import cache_invalidate

                cache_invalidate("rate_limit_policies", row.id)
            except Exception:  # noqa: BLE001
                logger.debug("rate_limit_policies cache_invalidate failed", exc_info=True)

        return MCPToolResult(
            ok=True,
            data={"policy_id": policy_id, "changed": changed},
            summary=f"policy {policy_id} updated; {len(changed)} field(s) changed",
        )


__all__ = [
    "RateLimitPolicyListTool",
    "RateLimitPolicyUpdateTool",
    "RateLimitReserveTool",
    "RateLimitStatusTool",
]
