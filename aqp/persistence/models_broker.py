"""BYOK broker credential ORM (AGENTS hard rule 55).

Per-user, envelope-encrypted storage for non-OAuth broker / data-vendor
API keys (Alpaca, Polygon, Interactive Brokers, Tradier, Tradestation,
Schwab, ETrade, Binance, Bybit, ...). Pairs with
:class:`aqp.credentials.stores.broker_credential_store.BrokerCredentialStore`
(priority 4) which dispatches between this table (B2C / "local"
backend) and the existing cloud-KMS stores (B2B / enterprise backend)
based on each :class:`aqp.persistence.models_tenancy.Organization`'s
``broker_credential_backend`` column.

The wrapping pattern is envelope encryption:

- A 256-bit DEK (data-encryption key) is generated per credential.
- The DEK encrypts the user-supplied API key with AES-256-GCM.
- The DEK itself is wrapped by a KEK (key-encryption key) held in
  Vault Transit / AWS KMS / Azure Key Vault / GCP KMS via the
  existing :func:`aqp.credentials.vault_transit.encrypt` helper.
- Only the wrapped DEK ever touches Postgres; the KEK is rotatable
  without re-encrypting every row.

Rotation: :func:`aqp.security.rotation.rotate_broker_credential`
(planned for the rollout window) reads with the old KEK and writes
back wrapped under the new KEK; the ``kek_id`` column tracks which
key was used so rotation can scan + rewrite incrementally.

The table is RLS-protected by ``workspace_id`` (per AGENTS rule 51 /
migration 0063) so a stolen application connection can NEVER read
another tenant's credentials even with arbitrary SQL.
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
    LargeBinary,
    String,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import TenantOwnedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Canonical credential kinds — the discriminator that tells the
# resolver how to interpret the decrypted payload. Operators / agents
# never read this field directly; the resolver uses it to build the
# right ``Credential.fields`` shape.
CREDENTIAL_KIND_API_KEY: str = "api_key"
"""Single-string API key (e.g. Polygon, FRED via API-only providers)."""

CREDENTIAL_KIND_API_KEY_PAIR: str = "api_key_pair"
"""API key + secret pair (Alpaca, Binance, Coinbase, ...)."""

CREDENTIAL_KIND_BASIC_AUTH: str = "basic_auth"
"""HTTP Basic Auth username + password (legacy IBKR Gateway)."""

CREDENTIAL_KIND_SESSION_TOKEN: str = "session_token"
"""Long-lived session token (Schwab refresh tokens after OAuth)."""

CREDENTIAL_KIND_MTLS_PEM: str = "mtls_pem"
"""Client certificate + private key for mTLS-authenticated brokers."""


# Environment selector — paper vs live brokerage. Stored as a column
# (not in ``meta``) so range queries / list endpoints can filter on it
# without parsing JSON.
ENVIRONMENT_PAPER: str = "paper"
ENVIRONMENT_LIVE: str = "live"
ENVIRONMENT_SANDBOX: str = "sandbox"


# Provider slugs the platform ships with on day one. New entries land
# alongside a matching :class:`aqp.credentials.stores.broker_credential_store`
# provider-metadata helper that declares the credential-kind +
# metadata schema.
KNOWN_BROKER_PROVIDERS: frozenset[str] = frozenset(
    {
        "alpaca",
        "interactive_brokers",
        "tradier",
        "tradestation",
        "polygon",
        "iex_cloud",
        "schwab",
        "etrade",
        "binance",
        "coinbase",
        "bybit",
        "okx",
        "kraken",
        "tradovate",
        "ftx",   # disabled by default but reserved
        "custom",  # operator-supplied custom provider
        # Phase 1 (plan section 5) — data-vendor BYOK additions.
        # Each carries a matching policy template under
        # aqp_ratelimit/configs/policies/<vendor>.yaml.
        "databento",
        "tiingo",
        "alpha_vantage",
        "quandl",
        "coingecko",
        "fred",
    }
)


class BrokerCredential(Base, TenantOwnedMixin):
    """User-owned, envelope-encrypted broker API credential.

    The ``TenantOwnedMixin`` provides ``owner_user_id`` + ``workspace_id``
    columns + indexes (per :mod:`aqp/persistence/_tenancy_mixins`); the
    RLS policy on this table filters by ``workspace_id``. A user can
    own multiple credentials per provider — operators commonly keep
    one paper key + one live key per broker, and may share a credential
    across personal workspaces.
    """

    __tablename__ = "broker_credentials"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # provider — the broker / vendor slug (see KNOWN_BROKER_PROVIDERS).
    # Free-form to keep the door open for tenants that bring their own
    # exotic prime broker; the route layer rejects empty values.
    provider = Column(String(64), nullable=False, index=True)
    # User-supplied label so the list UI can disambiguate paper vs
    # live vs strategy-specific keys.
    label = Column(String(120), nullable=False)
    credential_kind = Column(String(32), nullable=False, default=CREDENTIAL_KIND_API_KEY)
    environment = Column(String(32), nullable=False, default=ENVIRONMENT_PAPER, index=True)

    # Envelope encryption. ``ciphertext`` is the AES-256-GCM output;
    # ``nonce`` is the 12-byte AEAD nonce; ``wrapped_dek`` is the
    # base64-encoded Vault Transit ciphertext (or the raw KMS wrapper
    # output for cloud backends); ``kek_id`` identifies the KEK so
    # the rotation task knows which key to unwrap with.
    ciphertext = Column(LargeBinary, nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    wrapped_dek = Column(LargeBinary, nullable=False)
    kek_id = Column(String(255), nullable=False)

    # Safe metadata — endpoint URL, account_id, region, etc. NEVER
    # the credential value itself. The route layer rejects payloads
    # whose key matches the credential-secret pattern.
    meta = Column(JSON, default=dict)

    # Lifecycle bookkeeping.
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # One credential per (user, provider, label) tuple — operators
        # can't accidentally double-add the same key under the same name.
        UniqueConstraint("owner_user_id", "provider", "label", name="uq_broker_credentials"),
        Index(
            "ix_broker_credentials_provider_workspace",
            "provider",
            "workspace_id",
        ),
        Index(
            "ix_broker_credentials_owner_active",
            "owner_user_id",
            "is_active",
        ),
    )


__all__ = [
    "BrokerCredential",
    "CREDENTIAL_KIND_API_KEY",
    "CREDENTIAL_KIND_API_KEY_PAIR",
    "CREDENTIAL_KIND_BASIC_AUTH",
    "CREDENTIAL_KIND_MTLS_PEM",
    "CREDENTIAL_KIND_SESSION_TOKEN",
    "ENVIRONMENT_LIVE",
    "ENVIRONMENT_PAPER",
    "ENVIRONMENT_SANDBOX",
    "KNOWN_BROKER_PROVIDERS",
]
