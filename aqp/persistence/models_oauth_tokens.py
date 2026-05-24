"""Per-user external OAuth2 token registry (Workstream D).

Users authorise AQP to access an external data source (Bloomberg,
Refinitiv, GitHub, FRED, …) through an in-app PKCE flow. The
resulting tokens are envelope-encrypted via Vault Transit (or a
local fallback for dev) and the resulting Vault path is recorded
here. The model NEVER stores plaintext secret material — only the
metadata needed to:

- Tell the user which connections they have.
- Resolve the right Vault path via :class:`UserOAuthTokenStore`.
- Run the token-refresh worker before expiry.
- Audit token use without leaking the token itself.

Partial-unique index on ``(user_id, source)`` where
``revoked_at IS NULL`` means at most one *active* connection per
``(user, source)`` pair. Revoked rows persist so an audit query can
show "user X had a Bloomberg connection between A and B" without
permanently losing the metadata trail.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class UserOAuthToken(Base):
    """One row per (user, external source) connection.

    ``vault_path`` is the address (inside Vault, or whatever store the
    deployment uses) where the envelope-encrypted token blob lives.
    The blob itself NEVER appears in this table.
    """

    __tablename__ = "user_oauth_tokens"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Canonical source slug — must match the
    # ``ExternalOAuthProvider.provider_slug`` of the matching provider.
    source = Column(String(64), nullable=False, index=True)

    # Vault path where the encrypted token blob lives. Format:
    # ``oauth2/users/{org}/{user}/{source}``. Reads go through
    # :class:`UserOAuthTokenStore` which resolves this path via the
    # :class:`HashicorpVaultSecretStore` + Transit unwrap.
    vault_path = Column(String(240), nullable=False)

    # Scope strings granted by the external provider. Surfaced to the
    # frontend so users can revoke + re-authorise when the scope set
    # changes.
    scopes = Column(JSON, default=list)

    # OAuth2 token lifecycle. Read by the refresh worker; never
    # contains secret material.
    expires_at = Column(DateTime, nullable=True, index=True)
    refresh_token_expires_at = Column(DateTime, nullable=True)
    last_refreshed_at = Column(DateTime, nullable=True)

    # Optional human-readable label set by the user (e.g. "Bloomberg
    # Personal", "Refinitiv Trading Desk"). Defaults to the source slug.
    label = Column(String(120), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_user_oauth_tokens_user_source", "user_id", "source"),
        Index(
            "ix_user_oauth_tokens_active_unique",
            "user_id",
            "source",
            unique=True,
            postgresql_where=Column("revoked_at").is_(None),  # type: ignore[arg-type]
        ),
    )


__all__ = ["UserOAuthToken"]
