"""BYOK broker credential store (AGENTS hard rule 55).

Sits at priority 4 — above :class:`UserOAuthTokenStore` (priority 5)
so a broker key resolves before any OAuth-style match the user
happens to have for the same provider slug. Resolves the active
``Organization.broker_credential_backend`` per call:

- ``local`` (default for B2C / Trial / Pro tiers) — reads from the
  Postgres ``broker_credentials`` table installed by Alembic 0065 and
  decrypts via :func:`aqp.credentials.vault_transit.decrypt`.
- ``hashicorp_vault`` / ``aws_sm`` / ``azure_kv`` / ``gcp_sm`` (B2B
  enterprise tiers) — delegates to the matching existing cloud-KMS
  store via the standard :class:`CredentialResolver` chain at
  reduced priority, so the enterprise tenant keeps the credential in
  their own Vault / Secrets Manager and AQP only reads it via a path
  convention.

The path convention for enterprise-backend lookups is::

    {provider_slug}:user:{user_id}:{label}

so an Alpaca paper-trading key for user ``abc`` labelled ``primary``
resolves to ``alpaca:user:abc:primary``. The cloud-store concrete
classes already implement the resolver chain — this store just
constructs the key + audience and asks them.

The credential payload shape depends on the persisted
``credential_kind``:

- ``api_key`` → ``{"api_key": "..."}``
- ``api_key_pair`` → ``{"api_key": "...", "api_secret": "..."}``
- ``basic_auth`` → ``{"username": "...", "password": "..."}``
- ``session_token`` → ``{"session_token": "...", "access_token": "..."}``
- ``mtls_pem`` → ``{"client_cert_pem": "...", "client_key_pem": "..."}``

The payload is the JSON-decoded plaintext from the envelope. Callers
read fields via :meth:`Credential.require` / :meth:`Credential.get`.

Per AGENTS hard rule 22 (DataMCP boundary), agents NEVER read this
store directly — they go through a registered DataMCPTool that
mediates the credential lookup. The store is what the tool calls;
the rule applies to call-sites.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from aqp.credentials.protocol import Credential, CredentialKey, SecretStore

logger = logging.getLogger(__name__)


# Priority above UserOAuthToken (5) so broker keys for a service whose
# slug overlaps with an OAuth registration (e.g. some prime brokers
# expose both an API-key surface and an OAuth surface) resolve to the
# explicit broker key first.
PRIORITY_BROKER_CREDENTIAL = 4
BROKER_PURPOSE = "broker"


# Backend selector values. Mirror the column values on
# ``Organization.broker_credential_backend`` (Alembic 0065).
BACKEND_LOCAL: str = "local"
BACKEND_HASHICORP_VAULT: str = "hashicorp_vault"
BACKEND_AWS_SECRETS_MANAGER: str = "aws_sm"
BACKEND_AZURE_KEY_VAULT: str = "azure_kv"
BACKEND_GCP_SECRET_MANAGER: str = "gcp_sm"

EXTERNAL_BACKENDS: frozenset[str] = frozenset(
    {
        BACKEND_HASHICORP_VAULT,
        BACKEND_AWS_SECRETS_MANAGER,
        BACKEND_AZURE_KEY_VAULT,
        BACKEND_GCP_SECRET_MANAGER,
    }
)


class BrokerCredentialStore(SecretStore):
    """Resolves per-user broker credentials via local table or external KMS."""

    store_kind = "broker"
    store_priority = PRIORITY_BROKER_CREDENTIAL

    def get(self, key: CredentialKey) -> Credential | None:
        if str(key.purpose) != BROKER_PURPOSE:
            return None
        # key.service is the slug; we accept the bare provider
        # ("alpaca") or a fully-qualified "provider:label" so the
        # call site can disambiguate when a user has multiple
        # credentials for the same provider.
        service = str(key.service or "").strip()
        if not service:
            return None
        if ":" in service:
            provider, label = service.split(":", 1)
        else:
            provider, label = service, ""

        user_id = _current_user_id()
        if not user_id:
            return None

        backend = _resolve_backend_for_user(user_id)
        if backend == BACKEND_LOCAL:
            return _read_local(user_id=user_id, provider=provider, label=label)
        if backend in EXTERNAL_BACKENDS:
            return _read_external(
                backend=backend,
                user_id=user_id,
                provider=provider,
                label=label,
            )
        # Unknown backend — log and fall through so the resolver
        # tries the next store. Don't raise: the operator hasn't
        # decided yet, and we don't want to break trading.
        logger.warning(
            "BrokerCredentialStore: unknown backend=%r for user=%s; falling through",
            backend,
            user_id,
        )
        return None


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------


def _current_user_id() -> str | None:
    try:
        from aqp.tenancy.runtime_context import get_runtime_context

        ctx = get_runtime_context()
        if ctx is None:
            return None
        return getattr(ctx, "user_id", None)
    except Exception:  # noqa: BLE001
        return None


def _current_org_id() -> str | None:
    try:
        from aqp.tenancy.runtime_context import get_runtime_context

        ctx = get_runtime_context()
        if ctx is None:
            return None
        return getattr(ctx, "org_id", None)
    except Exception:  # noqa: BLE001
        return None


def _resolve_backend_for_user(user_id: str) -> str:
    """Return the backend selector ('local' / 'hashicorp_vault' / ...).

    Falls back to ``BACKEND_LOCAL`` when:

    - No active :class:`RequestContext` is bound (e.g. CLI / Celery
      task without tenant scope) — local is the safe default.
    - The active org's row has no ``broker_credential_backend`` set
      (newly created orgs).
    - The DB lookup fails — operators don't want a transient DB
      blip to flip their brokerage to "unknown".
    """
    org_id = _current_org_id()
    if not org_id:
        return BACKEND_LOCAL
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Organization

        with get_session() as session:
            row = session.query(Organization).filter(Organization.id == org_id).one_or_none()
            if row is None:
                return BACKEND_LOCAL
            backend = getattr(row, "broker_credential_backend", None)
            if not backend:
                return BACKEND_LOCAL
            return str(backend).strip().lower()
    except Exception:  # noqa: BLE001
        logger.debug("BrokerCredentialStore backend lookup failed", exc_info=True)
        return BACKEND_LOCAL


# ---------------------------------------------------------------------------
# Local backend — Postgres + Vault Transit (envelope-encrypted)
# ---------------------------------------------------------------------------


def _read_local(*, user_id: str, provider: str, label: str) -> Credential | None:
    try:
        from aqp.credentials.vault_transit import decrypt
        from aqp.persistence.db import get_session
        from aqp.persistence.models_broker import BrokerCredential
    except Exception:  # noqa: BLE001
        return None

    try:
        with get_session() as session:
            q = session.query(BrokerCredential).filter(
                BrokerCredential.owner_user_id == user_id,
                BrokerCredential.provider == provider,
                BrokerCredential.is_active.is_(True),
                BrokerCredential.revoked_at.is_(None),
            )
            if label:
                q = q.filter(BrokerCredential.label == label)
            row = q.order_by(BrokerCredential.created_at.desc()).first()
            if row is None:
                return None
            # Decrypt the envelope. The wrapped DEK is the Vault
            # Transit ciphertext; the AESGCM payload lives in
            # ``ciphertext`` + ``nonce``.
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except Exception:  # noqa: BLE001
                logger.warning(
                    "BrokerCredentialStore: cryptography library missing"
                )
                return None
            try:
                dek_pt = decrypt(
                    row.wrapped_dek.decode("ascii")
                    if isinstance(row.wrapped_dek, (bytes, bytearray))
                    else row.wrapped_dek,
                    tenant=str(row.organization_id or "default"),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "BrokerCredentialStore: DEK unwrap failed for credential id=%s",
                    row.id,
                )
                return None
            try:
                aesgcm = AESGCM(dek_pt)
                plaintext = aesgcm.decrypt(
                    bytes(row.nonce),
                    bytes(row.ciphertext),
                    str(row.id).encode("ascii"),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "BrokerCredentialStore: AESGCM decrypt failed for credential id=%s",
                    row.id,
                )
                return None
            try:
                payload = json.loads(plaintext.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                logger.warning(
                    "BrokerCredentialStore: payload is not JSON for id=%s",
                    row.id,
                )
                return None
            if not isinstance(payload, dict):
                return None
            # Stamp last_used_at for the rotation surface.
            row.last_used_at = datetime.utcnow()
            session.flush()
            fields = {str(k): str(v) for k, v in payload.items() if v is not None}
            fields["__credential_id__"] = str(row.id)
            fields["__provider__"] = str(row.provider)
            fields["__environment__"] = str(row.environment)
            fields["__credential_kind__"] = str(row.credential_kind)
            return Credential(fields=fields, source="broker:local")
    except Exception:  # noqa: BLE001
        logger.debug("BrokerCredentialStore local lookup failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# External backend — delegate to the matching cloud-KMS store
# ---------------------------------------------------------------------------


def _read_external(
    *,
    backend: str,
    user_id: str,
    provider: str,
    label: str,
) -> Credential | None:
    """Resolve a broker credential from an enterprise tenant's own KMS.

    The convention is that the enterprise stores the credential under
    a deterministic path. We construct the key + delegate to the
    standard resolver chain — the existing
    :class:`HashicorpVaultSecretStore` / :class:`AwsSecretsmanagerStore`
    / :class:`AzureKeyvaultStore` / :class:`GcpSecretmanagerStore`
    classes handle the actual lookup.

    The resulting :class:`Credential` is returned verbatim; we don't
    re-shape it (the enterprise tenant is responsible for storing it
    in the shape the broker SDK expects).
    """
    from aqp.credentials import CredentialNotFoundError, get_resolver

    suffix = f":{label}" if label else ""
    delegated_key = CredentialKey(
        service=f"broker:{provider}",
        purpose=f"user:{user_id}{suffix}",
    )
    try:
        cred = get_resolver().resolve(delegated_key, default=None)
    except CredentialNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        logger.debug(
            "BrokerCredentialStore external lookup failed for key=%s backend=%s",
            delegated_key,
            backend,
            exc_info=True,
        )
        return None
    if cred is None:
        return None
    fields = dict(cred.fields)
    fields["__provider__"] = provider
    fields["__credential_kind__"] = "external"
    return Credential(
        fields=fields,
        source=f"broker:external:{backend}",
        ttl_seconds=cred.ttl_seconds,
    )


__all__ = [
    "BACKEND_AWS_SECRETS_MANAGER",
    "BACKEND_AZURE_KEY_VAULT",
    "BACKEND_GCP_SECRET_MANAGER",
    "BACKEND_HASHICORP_VAULT",
    "BACKEND_LOCAL",
    "BROKER_PURPOSE",
    "BrokerCredentialStore",
    "EXTERNAL_BACKENDS",
    "PRIORITY_BROKER_CREDENTIAL",
]
