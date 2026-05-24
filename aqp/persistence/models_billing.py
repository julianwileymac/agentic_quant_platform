"""B2B billing + seat-management ORM.

The Phase 5 platform refactor adds first-class billing entities so the
self-serve org-creation wizard, the seat-grant UX, and the audit
ledger can all reference the same source of truth.

Scope intentionally narrow:

- :class:`BillingAccount` — one row per :class:`Organization`. Tracks
  the plan tier, seat ceiling, Stripe customer id, trial bookkeeping.
  Stripe / billing-provider integration is out of scope for this
  refactor; the columns exist so the integration is non-breaking.
- :class:`SeatGrant` — one row per (BillingAccount, User) tuple. The
  org-admin UI and the SCIM provisioner write here; the route layer
  enforces ``len(active_seat_grants) <= billing_account.seat_limit``
  before issuing a new invite.

This module deliberately does NOT contain any Stripe webhook handler
or invoice persistence — those live in a future ``aqp/billing/``
subsystem. The contract here is just the AQP-side ledger so other
parts of the platform can answer "is this user provisioned to use
the platform on behalf of this org?" without polling Stripe.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Canonical plan tiers — the rollout uses these to gate feature
# availability (live trading, multi-region deploy, etc.).
PLAN_TIER_TRIAL: str = "trial"
PLAN_TIER_FREE: str = "free"
PLAN_TIER_PRO: str = "pro"
PLAN_TIER_ENTERPRISE: str = "enterprise"

PLAN_TIERS: frozenset[str] = frozenset(
    {PLAN_TIER_TRIAL, PLAN_TIER_FREE, PLAN_TIER_PRO, PLAN_TIER_ENTERPRISE}
)

# Default seat limits per plan tier. Operators can override per-org
# via the admin UI; the column on :class:`BillingAccount` is what the
# route layer enforces against.
DEFAULT_SEAT_LIMITS: dict[str, int] = {
    PLAN_TIER_TRIAL: 5,
    PLAN_TIER_FREE: 1,
    PLAN_TIER_PRO: 15,
    PLAN_TIER_ENTERPRISE: 500,
}

# Status values for the billing-account lifecycle. Loosely modeled on
# Stripe's subscription statuses so the future webhook integration can
# upsert directly.
BILLING_STATUS_ACTIVE: str = "active"
BILLING_STATUS_TRIALING: str = "trialing"
BILLING_STATUS_PAST_DUE: str = "past_due"
BILLING_STATUS_CANCELLED: str = "cancelled"
BILLING_STATUS_SUSPENDED: str = "suspended"


class BillingAccount(Base):
    """One billing record per :class:`Organization`.

    The relationship is 1:1 — the unique constraint on
    ``organization_id`` enforces it at the database layer so a
    misbehaving service can't accidentally double-provision.
    """

    __tablename__ = "billing_accounts"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_tier = Column(
        String(32), nullable=False, default=PLAN_TIER_TRIAL, index=True
    )
    seat_limit = Column(Integer, nullable=False, default=5)
    # Stripe (or future billing-provider) bookkeeping — opaque to AQP.
    stripe_customer_id = Column(String(120), nullable=True, unique=True)
    billing_email = Column(String(320), nullable=True)
    status = Column(
        String(32), nullable=False, default=BILLING_STATUS_TRIALING, index=True
    )
    trial_ends_at = Column(DateTime, nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    suspended_reason = Column(String(255), nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SeatGrant(Base):
    """One seat assignment per (BillingAccount, User) tuple.

    Created by the admin invite-accept handler and the SCIM
    provisioner. Revoked (rather than deleted) on user removal so
    billing reconciliation has a complete audit trail.
    """

    __tablename__ = "seat_grants"

    id = Column(String(36), primary_key=True, default=_uuid)
    billing_account_id = Column(
        String(36),
        ForeignKey("billing_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The role granted alongside the seat — informational; the
    # authoritative role is on :class:`Membership` so SeatGrant
    # changes don't accidentally revoke RBAC.
    role = Column(String(64), nullable=False, default="member")
    granted_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    meta = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "billing_account_id", "user_id", "is_active",
            name="uq_seat_grants_active",
        ),
        Index(
            "ix_seat_grants_billing_active",
            "billing_account_id",
            "is_active",
        ),
    )


__all__ = [
    "BILLING_STATUS_ACTIVE",
    "BILLING_STATUS_CANCELLED",
    "BILLING_STATUS_PAST_DUE",
    "BILLING_STATUS_SUSPENDED",
    "BILLING_STATUS_TRIALING",
    "BillingAccount",
    "DEFAULT_SEAT_LIMITS",
    "PLAN_TIERS",
    "PLAN_TIER_ENTERPRISE",
    "PLAN_TIER_FREE",
    "PLAN_TIER_PRO",
    "PLAN_TIER_TRIAL",
    "SeatGrant",
]
