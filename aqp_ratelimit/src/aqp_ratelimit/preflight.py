"""Cost-predictability preflight for partitioned backfills.

Used by ``aqp materialize --partition-range YYYY-MM-DD..YYYY-MM-DD``
and the ``data.ingest.materialize`` MCP tool. Computes the
projected token cost upfront and rejects a backfill that exceeds
the monthly quota with an actionable message ("would need 240,000
tokens, your monthly budget has 80,000 remaining").

Per the blueprint section 6.7 / plan section 10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreflightResult:
    allow: bool
    projected_cost: int
    remaining: float
    capacity: float
    service: str
    key_id: str
    user_id: str
    reservation_id: str | None = None
    actionable_message: str | None = None


def preflight_materialization(
    *,
    user_id: str,
    service: str,
    key_id: str,
    n_partitions: int,
    cost_per_partition: int,
    ttl_s: int = 7 * 24 * 3600,
) -> PreflightResult:
    """Reserve N tokens up front; return a rich error on rejection."""
    projected = int(n_partitions) * int(cost_per_partition)
    try:
        from aqp_ratelimit.client import get_ratelimit_client

        client = get_ratelimit_client()
        outcome = client.reserve(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=projected,
            ttl_s=ttl_s,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("preflight reserve failed: %s", exc)
        return PreflightResult(
            allow=False,
            projected_cost=projected,
            remaining=0.0,
            capacity=0.0,
            service=service,
            key_id=key_id,
            user_id=user_id,
            actionable_message=f"rate-limit backend failure: {exc}",
        )
    if outcome.allow:
        return PreflightResult(
            allow=True,
            projected_cost=projected,
            remaining=outcome.remaining,
            capacity=outcome.capacity,
            service=service,
            key_id=key_id,
            user_id=user_id,
            reservation_id=outcome.reservation_id,
            actionable_message=(
                f"reserved {projected} tokens; "
                f"{outcome.remaining:.0f}/{outcome.capacity:.0f} remaining"
            ),
        )
    return PreflightResult(
        allow=False,
        projected_cost=projected,
        remaining=outcome.remaining,
        capacity=outcome.capacity,
        service=service,
        key_id=key_id,
        user_id=user_id,
        actionable_message=(
            f"this backfill would need {projected:,} tokens but only "
            f"{outcome.remaining:,.0f} remaining in your {service} budget "
            f"(capacity={outcome.capacity:,.0f}). Trim the partition range, "
            f"upgrade your tier, or mint a higher-rps key."
        ),
    )


__all__ = ["PreflightResult", "preflight_materialization"]
