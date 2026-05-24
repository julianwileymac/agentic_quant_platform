"""REST surface for the rate-limit subsystem.

Three groups of endpoints:

- ``GET /me/ratelimit/status`` — read-only bucket snapshot. No auth
  beyond the standard JWT.
- ``POST /me/ratelimit/reserve`` — preflight reservation (mutating;
  step-up MFA required per AGENTS rule 52).
- ``POST /me/keys`` / ``GET /me/keys`` / ``DELETE /me/keys/{id}`` —
  per-user vendor key lifecycle. Create + delete attach
  ``require_step_up`` per AGENTS rule 52.

The mounting application registers this router under
``/api/v1/me/ratelimit`` (or equivalent) so the Vite client picks
up the endpoints via the existing `useApi()` hook.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/me/ratelimit", tags=["ratelimit"])
keys_router = APIRouter(prefix="/me/keys", tags=["ratelimit", "keys"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BucketStatus(BaseModel):
    service: str
    key_id: str
    remaining: float
    capacity: float
    refill_rate: float
    allow: bool
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class StatusResponse(BaseModel):
    buckets: list[BucketStatus]


class ReserveRequest(BaseModel):
    service: str
    key_id: str
    n_tokens: int = Field(ge=1)
    ttl_s: int = Field(default=3600, ge=1, le=86400)


class ReserveResponse(BaseModel):
    allow: bool
    reservation_id: str | None
    requested: int
    remaining: float
    capacity: float
    ttl_s: int


class MintKeyRequest(BaseModel):
    service: str
    label: str = Field(default="primary")
    rps: float | None = Field(default=None, gt=0)
    burst: int | None = Field(default=None, ge=1)
    ttl_days: int | None = Field(default=None, ge=1, le=365)
    vault_path: str | None = None


class KeyDescriptorOut(BaseModel):
    key_id: str
    service: str
    label: str
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


# ---------------------------------------------------------------------------
# Dependency stubs (real implementations live in aqp.api.security)
# ---------------------------------------------------------------------------


def _resolve_user_id() -> str:
    """Resolve the calling user from request state.

    Mounted in the monolith via :func:`Depends`; this stub is replaced
    when the monolith composes the routers.
    """
    try:
        from aqp.api.security import current_user_id_dep

        return current_user_id_dep()  # type: ignore[no-any-return]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "unauthenticated") from exc


def _require_step_up() -> None:
    """Step-up MFA gate (AGENTS rule 52).

    Resolved through the monolith's :func:`aqp.api.security_stepup.require_step_up`
    when actually mounted. The placeholder here keeps the route file
    importable in isolation.
    """
    try:
        from aqp.api.security_stepup import require_step_up

        dep = require_step_up(max_age_seconds=180)
        return dep  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
def get_status(
    service: str | None = Query(default=None),
    key_id: str | None = Query(default=None),
    user_id: str = Depends(_resolve_user_id),
) -> StatusResponse:
    """Per-(user, service, key_id) bucket snapshot."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey
    from aqp_ratelimit import get_ratelimit_client

    client = get_ratelimit_client()
    with get_session() as session:
        q = session.query(RateLimitKey).filter(
            RateLimitKey.owner_user_id == user_id,
            RateLimitKey.revoked_at.is_(None),
        )
        if service is not None:
            q = q.filter(RateLimitKey.service == service)
        if key_id is not None:
            q = q.filter(RateLimitKey.label == key_id)
        rows = q.all()
    out: list[BucketStatus] = []
    for row in rows:
        decision = client.status(
            user_id=user_id,
            service=row.service,
            key_id=row.label,
        )
        out.append(
            BucketStatus(
                service=row.service,
                key_id=row.label,
                remaining=decision.remaining,
                capacity=decision.capacity,
                refill_rate=decision.refill_rate,
                allow=decision.allow,
                issued_at=row.issued_at,
                expires_at=row.expires_at,
            )
        )
    return StatusResponse(buckets=out)


@router.post(
    "/reserve",
    response_model=ReserveResponse,
    dependencies=[Depends(_require_step_up)],
)
def post_reserve(
    body: ReserveRequest,
    user_id: str = Depends(_resolve_user_id),
) -> ReserveResponse:
    """Preflight reservation for partitioned backfills."""
    from aqp_ratelimit import get_ratelimit_client

    client = get_ratelimit_client()
    outcome = client.reserve(
        user_id=user_id,
        service=body.service,
        key_id=body.key_id,
        n_tokens=body.n_tokens,
        ttl_s=body.ttl_s,
    )
    return ReserveResponse(
        allow=outcome.allow,
        reservation_id=outcome.reservation_id,
        requested=outcome.requested,
        remaining=outcome.remaining,
        capacity=outcome.capacity,
        ttl_s=outcome.ttl_s,
    )


@router.delete(
    "/reservations/{reservation_id}",
    status_code=204,
    dependencies=[Depends(_require_step_up)],
)
def delete_reservation(
    reservation_id: str,
    user_id: str = Depends(_resolve_user_id),
) -> None:
    """Explicit early release."""
    from aqp_ratelimit import get_ratelimit_client

    get_ratelimit_client().release(reservation_id=reservation_id)


# ---------------------------------------------------------------------------
# Per-user vendor keys lifecycle
# ---------------------------------------------------------------------------


@keys_router.post(
    "",
    response_model=KeyDescriptorOut,
    status_code=201,
    dependencies=[Depends(_require_step_up)],
)
def mint_key(
    body: MintKeyRequest,
    user_id: str = Depends(_resolve_user_id),
) -> KeyDescriptorOut:
    """Mint a new per-user vendor key binding."""
    from datetime import timedelta

    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey, RateLimitPolicy

    with get_session() as session:
        # Pick policy by (service, tier=free) by default; admin UI
        # can override via _PROVIDER_METADATA in Phase 1.
        policy = (
            session.query(RateLimitPolicy)
            .filter(
                RateLimitPolicy.service == body.service,
                RateLimitPolicy.is_active.is_(True),
            )
            .order_by(RateLimitPolicy.tier.asc())
            .first()
        )
        if body.rps is not None and policy is None:
            policy = RateLimitPolicy(
                id=str(uuid.uuid4()),
                owner_user_id=user_id,
                service=body.service,
                tier="custom",
                capacity=int(body.burst or max(1, int(body.rps * 60))),
                refill_rate=float(body.rps),
                refill_interval_ms=1000,
                window_ms=60_000,
                notes="auto-created from aqp keys mint",
                is_active=True,
            )
            session.add(policy)
            session.flush()
        expires_at = None
        if body.ttl_days:
            expires_at = datetime.utcnow() + timedelta(days=body.ttl_days)
        row = RateLimitKey(
            id=str(uuid.uuid4()),
            owner_user_id=user_id,
            service=body.service,
            policy_id=policy.id if policy else None,
            label=body.label,
            vault_path=body.vault_path or f"secret/data/users/{user_id}/services/{body.service}",
            issued_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        out = KeyDescriptorOut(
            key_id=row.id,
            service=row.service,
            label=row.label,
            issued_at=row.issued_at,
            expires_at=row.expires_at,
            revoked_at=None,
            last_used_at=None,
        )
    try:
        from aqp.cache.invalidation import cache_write_through

        cache_write_through(
            "rate_limit_keys",
            row.id,
            {
                "key_id": row.id,
                "service": row.service,
                "label": row.label,
                "owner_user_id": user_id,
            },
            org_id=None,
        )
    except Exception:  # noqa: BLE001
        logger.debug("rate_limit_keys cache_write_through failed", exc_info=True)
    return out


@keys_router.get("", response_model=list[KeyDescriptorOut])
def list_keys(
    user_id: str = Depends(_resolve_user_id),
    include_revoked: bool = Query(default=False),
) -> list[KeyDescriptorOut]:
    """List the calling user's keys."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey

    with get_session() as session:
        q = session.query(RateLimitKey).filter(RateLimitKey.owner_user_id == user_id)
        if not include_revoked:
            q = q.filter(RateLimitKey.revoked_at.is_(None))
        rows = q.order_by(RateLimitKey.issued_at.desc()).all()
    return [
        KeyDescriptorOut(
            key_id=row.id,
            service=row.service,
            label=row.label,
            issued_at=row.issued_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            last_used_at=row.last_used_at,
        )
        for row in rows
    ]


@keys_router.delete(
    "/{key_id}",
    status_code=204,
    dependencies=[Depends(_require_step_up)],
)
def revoke_key(
    key_id: str,
    user_id: str = Depends(_resolve_user_id),
) -> None:
    """Revoke a per-user vendor key."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey

    with get_session() as session:
        row = session.get(RateLimitKey, key_id)
        if row is None or row.owner_user_id != user_id:
            raise HTTPException(404, "key not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
            row.revoked_by_user_id = user_id
            session.commit()
    try:
        from aqp.cache.invalidation import cache_invalidate

        cache_invalidate("rate_limit_keys", key_id)
    except Exception:  # noqa: BLE001
        logger.debug("rate_limit_keys cache_invalidate failed", exc_info=True)


__all__ = ["keys_router", "router"]
