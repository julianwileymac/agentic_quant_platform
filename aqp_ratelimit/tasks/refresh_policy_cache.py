"""Celery beat task: synchronise ``rl_policies`` → Redis policy cache.

Runs every 60 seconds (configurable via
``AQP_RATELIMIT_POLICY_REFRESH_SECONDS``) and writes each active
policy to Redis under ``aqp:cache:rate_limit_policies:by_id:{policy_id}``
so the strategy hot path can resolve policies without a Postgres
read on every request.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def refresh_policy_cache() -> dict[str, Any]:
    """Refresh the policy cache; returns ``{count, errors}``."""
    from aqp.cache.invalidation import cache_write_through
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitPolicy

    refreshed = 0
    errors: list[str] = []
    with get_session() as session:
        rows = (
            session.query(RateLimitPolicy)
            .filter(RateLimitPolicy.is_active.is_(True))
            .all()
        )
        for row in rows:
            try:
                cache_write_through(
                    "rate_limit_policies",
                    row.id,
                    {
                        "policy_id": row.id,
                        "service": row.service,
                        "tier": row.tier,
                        "capacity": int(row.capacity),
                        "refill_rate": float(row.refill_rate),
                        "refill_interval_ms": int(row.refill_interval_ms or 1000),
                        "window_ms": int(row.window_ms or 60_000),
                    },
                    org_id=None,
                )
                refreshed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{row.service}/{row.tier}: {exc}")
                logger.warning("policy cache refresh failed for %s: %s", row.id, exc)
    logger.info("rate-limit policy cache refresh: %s row(s)", refreshed)
    return {"count": refreshed, "errors": errors}


__all__ = ["refresh_policy_cache"]
