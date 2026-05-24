"""Per-agent dual-debit strategy (root AGENTS.md rule 54).

When :class:`aqp.data.mcp.base.MCPToolContext` has
``actor_kind="agent"``, the agent's own bucket is debited alongside
the user's. This bounds the autonomous agents' independent vendor
exploration budget — an agent cannot quietly drain the user's
$500/mo Polygon budget by issuing thousands of ``preview_source``
calls in one chain-of-thought.

The wrapper composes any other concrete strategy (typically
:class:`RedisTokenBucketStrategy`) so the per-agent ceiling lives on
top of the per-user ceiling without duplicating the bucket math.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp_ratelimit.models import Decision, ReserveOutcome
from aqp_ratelimit.strategies.base import IngestionRateLimitStrategy

logger = logging.getLogger(__name__)


_AGENT_BUCKET_USER_SUFFIX = "__agent__"


class PerAgentStrategy(IngestionRateLimitStrategy):
    """Dual-debit wrapper that requires both per-user and per-agent buckets to allow."""

    strategy_kind = "per_agent"
    strategy_alias = "PerAgentStrategy"
    strategy_priority = 5  # checked before the per-user strategy

    def __init__(self, *, inner: IngestionRateLimitStrategy) -> None:
        self._inner = inner

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def check(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int = 1,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        actor_kind = (ctx or {}).get("actor_kind", "user")
        agent_subject = (ctx or {}).get("agent_subject")
        if actor_kind == "agent" and agent_subject:
            agent_decision = self._inner.check(
                user_id=self._agent_user(agent_subject),
                service=service,
                key_id=self._agent_key_id(agent_subject),
                n_tokens=n_tokens,
                ctx=(ctx or {}).get("agent_policy"),
            )
            if not agent_decision.allow:
                return agent_decision
        return self._inner.check(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ctx=ctx,
        )

    def reserve(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int,
        ttl_s: int,
        ctx: dict[str, Any] | None = None,
    ) -> ReserveOutcome:
        actor_kind = (ctx or {}).get("actor_kind", "user")
        agent_subject = (ctx or {}).get("agent_subject")
        if actor_kind == "agent" and agent_subject:
            agent_outcome = self._inner.reserve(
                user_id=self._agent_user(agent_subject),
                service=service,
                key_id=self._agent_key_id(agent_subject),
                n_tokens=n_tokens,
                ttl_s=ttl_s,
                ctx=(ctx or {}).get("agent_policy"),
            )
            if not agent_outcome.allow:
                return agent_outcome
        return self._inner.reserve(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ttl_s=ttl_s,
            ctx=ctx,
        )

    def release(self, *, reservation_id: str) -> None:
        self._inner.release(reservation_id=reservation_id)

    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
    ) -> Decision:
        return self._inner.status(user_id=user_id, service=service, key_id=key_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _agent_user(self, agent_subject: str) -> str:
        return f"{_AGENT_BUCKET_USER_SUFFIX}{agent_subject}"

    def _agent_key_id(self, agent_subject: str) -> str:
        return f"agent:{agent_subject}"


__all__ = ["PerAgentStrategy"]
