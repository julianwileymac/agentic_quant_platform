"""Rate-limit accounting ORM (Phase 0 — Foundations).

Six tables that back the per-(user, service, key_id) rate-limit
subsystem:

- :class:`RateLimitPolicy` — declarative policies keyed by
  ``(service, tier)``. The Lua bucket script reads ``capacity`` +
  ``refill_rate`` from this table via the Redis policy cache that
  Celery beat refreshes every 60s.
- :class:`RateLimitKey` — per-user vendor key bindings. Each row
  points at a Vault path that holds the actual vendor secret;
  rotating the secret never touches this table, only the Vault
  path's underlying value.
- :class:`RateLimitLedger` — append-only audit + observability
  ledger. Partitioned by ``RANGE`` on ``ts`` so old partitions
  drop cleanly.
- :class:`UserTier` — joins users to a tier (free / starter /
  advanced) that scales the per-policy ``capacity`` for restricted
  endpoints.
- :class:`TemplateCatalog` — connector marketplace template
  catalog (Phase 5 populates this with 50+ financial-API
  templates; the table is created now so the FK relationships are
  in place).
- :class:`AuditLog` — tamper-evident hash-chain log
  (``prev_hash`` references the previous row's hash). Holds every
  ingestion-plane mutation surfaced by `data.ingest.*`,
  `data.transform.*`, and `data.ratelimit.*` MCP tools.

All six tables are workspace-scoped via :class:`TenantOwnedMixin`
and registered in :data:`aqp.tenancy.rls_policies.RLS_TABLES` so
PostgreSQL Row-Level Security rejects cross-tenant reads at the
database layer per AGENTS rule 51.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import TenantOwnedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Canonical tier slugs.
TIER_FREE: str = "free"
TIER_STARTER: str = "starter"
TIER_ADVANCED: str = "advanced"
TIER_ENTERPRISE: str = "enterprise"


# Canonical ledger decision strings.
LEDGER_DECISION_ALLOW: str = "allow"
LEDGER_DECISION_DENY: str = "deny"
LEDGER_DECISION_CACHED: str = "cached"
LEDGER_DECISION_RESERVED: str = "reserved"
LEDGER_DECISION_RELEASED: str = "released"


# Canonical template kinds (matches Phase 5 connector marketplace).
TEMPLATE_KIND_LOW_CODE_YAML: str = "low_code_yaml"
TEMPLATE_KIND_PYTHON_CDK: str = "python_cdk"
TEMPLATE_KIND_CDC: str = "cdc"


# Canonical audit-log event categories.
AUDIT_CATEGORY_INGEST: str = "ingest"
AUDIT_CATEGORY_RATELIMIT: str = "ratelimit"
AUDIT_CATEGORY_TRANSFORM: str = "transform"
AUDIT_CATEGORY_KEY_LIFECYCLE: str = "key_lifecycle"


class RateLimitPolicy(Base, TenantOwnedMixin):
    """Declarative rate-limit policy keyed by ``(service, tier)``."""

    __tablename__ = "rl_policies"

    id = Column(String(36), primary_key=True, default=_uuid)
    service = Column(String(120), nullable=False, index=True)
    tier = Column(String(32), nullable=False, server_default=TIER_FREE, index=True)
    capacity = Column(Integer, nullable=False)
    refill_rate = Column(Float, nullable=False, comment="Tokens per second")
    refill_interval_ms = Column(Integer, nullable=False, server_default="1000")
    window_ms = Column(Integer, nullable=False, server_default="60000")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("service", "tier", "workspace_id", name="uq_rl_policies"),
        Index("ix_rl_policies_service_active", "service", "is_active"),
    )


class RateLimitKey(Base, TenantOwnedMixin):
    """Per-user vendor key binding pointing at a Vault path."""

    __tablename__ = "rl_keys"

    id = Column(String(36), primary_key=True, default=_uuid)
    service = Column(String(120), nullable=False, index=True)
    policy_id = Column(
        String(36),
        ForeignKey("rl_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    label = Column(String(120), nullable=False, server_default="primary")
    vault_path = Column(String(500), nullable=False)
    issued_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at = Column(DateTime, nullable=True)
    meta = Column(JSON, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "service", "label", name="uq_rl_keys_owner_service_label"
        ),
        Index("ix_rl_keys_service_owner", "service", "owner_user_id"),
        Index("ix_rl_keys_revoked_at", "revoked_at"),
    )


class RateLimitLedger(Base, TenantOwnedMixin):
    """Append-only audit + observability ledger.

    The ``rl_ledger`` table is partitioned by RANGE on ``ts`` at
    migration time (Postgres only) so old partitions can be dropped
    cleanly. The ORM model surfaces the union view.
    """

    __tablename__ = "rl_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    service = Column(String(120), nullable=False, index=True)
    key_id = Column(String(36), nullable=False, index=True)
    tokens_consumed = Column(Integer, nullable=False, server_default="1")
    decision = Column(String(16), nullable=False, index=True)
    request_hash = Column(LargeBinary, nullable=True)
    asset_key = Column(String(500), nullable=True)
    actor_kind = Column(String(16), nullable=False, server_default="user")
    agent_subject = Column(String(255), nullable=True)
    on_behalf_of_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta = Column(JSON, nullable=False, server_default="{}")

    __table_args__ = (
        Index("ix_rl_ledger_ts_service", "ts", "service"),
        Index("ix_rl_ledger_owner_ts", "owner_user_id", "ts"),
    )


class UserTier(Base, TenantOwnedMixin):
    """Joins a user to a tier (free / starter / advanced / enterprise)."""

    __tablename__ = "user_tiers"

    id = Column(String(36), primary_key=True, default=_uuid)
    tier = Column(String(32), nullable=False, server_default=TIER_FREE)
    monthly_quota_multiplier = Column(Float, nullable=False, server_default="1.0")
    monthly_token_budget = Column(BigInteger, nullable=True)
    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    effective_until = Column(DateTime, nullable=True)
    granted_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta = Column(JSON, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("owner_user_id", "effective_from", name="uq_user_tiers_owner_from"),
        Index("ix_user_tiers_tier", "tier"),
    )


class TemplateCatalog(Base, TenantOwnedMixin):
    """Connector marketplace template catalog (Phase 5 seeds 50+ rows).

    A template represents one curated way to instantiate an ingestion
    connector. The discriminator ``kind`` is one of
    ``low_code_yaml`` / ``python_cdk`` / ``cdc``. Templates live in
    ``aqp_ingest/marketplace/seed/`` and the Phase 5 Celery beat
    task sync-imports them into this table on boot.
    """

    __tablename__ = "template_catalog"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    display_name = Column(String(240), nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    vendor_tier = Column(String(32), nullable=True)
    spec_json = Column(JSON, nullable=False, server_default="{}")
    rate_limit_class = Column(String(120), nullable=True, index=True)
    default_sync_mode = Column(String(64), nullable=True)
    doc_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_template_catalog_kind_active", "kind", "is_active"),
    )


class AuditLog(Base, TenantOwnedMixin):
    """Tamper-evident hash-chain audit log.

    Every row carries a ``hash`` (SHA-256 over the canonical row
    contents) and a ``prev_hash`` pointing at the previous row's
    hash. Phase 6 nightly export ships these to S3 with object
    lock for Reg SCI 17 CFR § 242.1005 + MiFID II Article 25
    (7-year retention).
    """

    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    event_category = Column(String(64), nullable=False, index=True)
    event_type = Column(String(120), nullable=False, index=True)
    actor_kind = Column(String(16), nullable=False, server_default="user")
    agent_subject = Column(String(255), nullable=True)
    on_behalf_of_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_id = Column(String(120), nullable=True, index=True)
    approval_id = Column(String(36), nullable=True, index=True)
    template_id = Column(String(36), nullable=True)
    connection_id = Column(String(36), nullable=True)
    request_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=False, server_default="{}")
    prev_hash = Column(LargeBinary, nullable=True)
    hash = Column(LargeBinary, nullable=False)

    __table_args__ = (
        Index("ix_audit_log_owner_ts", "owner_user_id", "ts"),
        Index("ix_audit_log_event_category_ts", "event_category", "ts"),
    )


__all__ = [
    "AUDIT_CATEGORY_INGEST",
    "AUDIT_CATEGORY_KEY_LIFECYCLE",
    "AUDIT_CATEGORY_RATELIMIT",
    "AUDIT_CATEGORY_TRANSFORM",
    "AuditLog",
    "LEDGER_DECISION_ALLOW",
    "LEDGER_DECISION_CACHED",
    "LEDGER_DECISION_DENY",
    "LEDGER_DECISION_RELEASED",
    "LEDGER_DECISION_RESERVED",
    "RateLimitKey",
    "RateLimitLedger",
    "RateLimitPolicy",
    "TEMPLATE_KIND_CDC",
    "TEMPLATE_KIND_LOW_CODE_YAML",
    "TEMPLATE_KIND_PYTHON_CDK",
    "TIER_ADVANCED",
    "TIER_ENTERPRISE",
    "TIER_FREE",
    "TIER_STARTER",
    "TemplateCatalog",
    "UserTier",
]
