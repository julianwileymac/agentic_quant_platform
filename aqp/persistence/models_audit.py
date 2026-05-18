"""Security audit and tenancy invite persistence models."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from aqp.config import settings
from aqp.persistence.models import Base

_JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _resolve_invite_secret(secret: str | None) -> str:
    candidate = secret if secret is not None else settings.auth_invite_secret
    resolved = str(candidate or "").strip()
    if not resolved:
        raise RuntimeError(
            "AQP auth_invite_secret is empty; set AQP_AUTH_INVITE_SECRET before hashing invite tokens."
        )
    return resolved


def _default_invite_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=int(settings.auth_invite_ttl_hours))


def hash_invite_token(raw_token: str, *, secret: str | None = None) -> str:
    """Return the hex-encoded HMAC-SHA256 for ``raw_token``.

    The key is ``settings.auth_invite_secret`` unless ``secret`` is provided.
    Only the hash is persisted in the database.
    """
    key = _resolve_invite_secret(secret).encode("utf-8")
    payload = raw_token.encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def generate_invite_token(*, byte_length: int = 32) -> tuple[str, str]:
    """Return ``(raw_token, token_hash)`` for a fresh tenancy invite."""
    if byte_length <= 0:
        raise ValueError("byte_length must be positive.")
    raw_token = secrets.token_hex(byte_length)
    return raw_token, hash_invite_token(raw_token)


class SecurityAuditEvent(Base):
    """Append-only security audit log.

    One row per security-relevant action. NEVER updated in place — the
    table is enforced read-only at the ORM layer via :meth:`__setattr__`
    once the row is persistent.
    """

    __tablename__ = "security_audit_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type = Column(String(64), nullable=False)
    event_category = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)
    source = Column(String(32), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    actor_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    connection = Column(String(120), nullable=True)
    request_id = Column(String(120), nullable=True)
    details = Column(_JSONB_COMPAT, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith("_sa_"):
            super().__setattr__(key, value)
            return
        state = inspect(self, raiseerr=False)
        if (
            state is not None
            and state.persistent
            and key in self.__dict__
            and self.__dict__[key] != value
        ):
            raise AttributeError(
                "SecurityAuditEvent rows are append-only and cannot be mutated after insert."
            )
        super().__setattr__(key, value)


Index(
    "ix_security_audit_events_user_created_at_desc",
    SecurityAuditEvent.user_id,
    SecurityAuditEvent.created_at.desc(),
)
Index(
    "ix_security_audit_events_org_created_at_desc",
    SecurityAuditEvent.organization_id,
    SecurityAuditEvent.created_at.desc(),
)
Index(
    "ix_security_audit_events_event_type_created_at_desc",
    SecurityAuditEvent.event_type,
    SecurityAuditEvent.created_at.desc(),
)
Index(
    "ix_security_audit_events_created_at_desc",
    SecurityAuditEvent.created_at.desc(),
)
Index(
    "ix_security_audit_events_actor_created_at_desc",
    SecurityAuditEvent.actor_user_id,
    SecurityAuditEvent.created_at.desc(),
)


class TenancyInvite(Base):
    """Pending invite for organization/workspace/team membership."""

    __tablename__ = "tenancy_invites"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    team_id = Column(
        String(36),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
    )
    email = Column(String(320), nullable=False)
    role = Column(String(32), nullable=False)
    invited_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_hash = Column(String(64), nullable=False)
    token_prefix = Column(String(8), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    message = Column(Text, nullable=True)
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_default_invite_expires_at,
    )
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


Index(
    "uq_tenancy_invites_org_email_pending",
    TenancyInvite.organization_id,
    TenancyInvite.email,
    unique=True,
    postgresql_where=text("status = 'pending'"),
    sqlite_where=text("status = 'pending'"),
)
Index(
    "ix_tenancy_invites_org_status_created_at_desc",
    TenancyInvite.organization_id,
    TenancyInvite.status,
    TenancyInvite.created_at.desc(),
)
Index(
    "ix_tenancy_invites_email_status",
    TenancyInvite.email,
    TenancyInvite.status,
)
Index("uq_tenancy_invites_token_hash", TenancyInvite.token_hash, unique=True)
Index(
    "ix_tenancy_invites_expires_at_pending",
    TenancyInvite.expires_at,
    postgresql_where=text("status = 'pending'"),
    sqlite_where=text("status = 'pending'"),
)


__all__ = [
    "SecurityAuditEvent",
    "TenancyInvite",
    "generate_invite_token",
    "hash_invite_token",
]
