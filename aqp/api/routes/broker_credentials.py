"""``/me/broker-credentials`` + ``/admin/orgs/{org_id}/broker-backend`` routes.

AGENTS hard rule 55 — first-class CRUD for BYOK broker / data-vendor
API keys. Mirrors the shape of :mod:`aqp.api.routes.oauth_connections`
so the frontend account-management tabs have a uniform feel.

Endpoints:

- ``GET    /me/broker-credentials/providers``        — list known
  providers + their JSON-schema metadata so the form can render
  the right fields per provider.
- ``GET    /me/broker-credentials``                  — list the
  caller's active credentials (label / provider / environment /
  last_used; NEVER the secret value).
- ``POST   /me/broker-credentials``                  — create new
  credential. Requires step-up MFA.
- ``DELETE /me/broker-credentials/{id}``             — soft revoke.
  Requires step-up MFA.
- ``PUT    /admin/orgs/{org_id}/broker-backend``     — admin-only,
  step-up MFA, switch the org's backend selector.

Per the credential-safety rule (`.cursor/rules/aqp-management-engine.mdc`),
the secret value NEVER appears in any response body, log line, or
audit details payload — the create endpoint accepts it once via the
request body, encrypts it in memory, persists the ciphertext, and
discards the plaintext immediately.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.security_stepup import require_step_up
from aqp.auth import CurrentUser, current_user
from aqp.auth.audit import emit_audit_event

logger = logging.getLogger(__name__)


router = secure_router(prefix="/me/broker-credentials", tags=["broker-credentials"])
admin_router = secure_router(prefix="/admin/orgs", tags=["broker-credentials", "admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BrokerCredentialIn(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=120)
    credential_kind: str = Field(default="api_key")
    environment: Literal["paper", "live", "sandbox"] = Field(default="paper")
    # The plaintext secret payload. Keys depend on credential_kind —
    # see :mod:`aqp.persistence.models_broker` for the convention.
    # The server NEVER echoes this back; it's encrypted + dropped.
    payload: dict[str, str] = Field(default_factory=dict)
    # Safe metadata — endpoint URL, account_id, etc. NEVER contains
    # the credential value (the route rejects payloads whose keys
    # match the secret name).
    meta: dict[str, Any] = Field(default_factory=dict)


class BrokerCredentialSummary(BaseModel):
    id: str
    provider: str
    label: str
    credential_kind: str
    environment: str
    is_active: bool
    last_used_at: str | None
    created_at: str
    meta: dict[str, Any] = Field(default_factory=dict)


class BrokerBackendUpdate(BaseModel):
    backend: Literal["local", "hashicorp_vault", "aws_sm", "azure_kv", "gcp_sm"]


# ---------------------------------------------------------------------------
# Provider metadata — shapes the frontend form
# ---------------------------------------------------------------------------


# Per-provider metadata declares the credential_kind + the field names
# the form should render. The frontend reads this to build the input
# layout dynamically — adding a new broker is one entry here + a new
# slug in ``KNOWN_BROKER_PROVIDERS``.
_PROVIDER_METADATA: dict[str, dict[str, Any]] = {
    "alpaca": {
        "display_name": "Alpaca",
        "credential_kind": "api_key_pair",
        "payload_fields": [
            {"name": "api_key", "label": "API Key", "secret": True},
            {"name": "api_secret", "label": "API Secret", "secret": True},
        ],
        "meta_fields": [
            {"name": "endpoint", "label": "Endpoint URL", "secret": False},
        ],
        "supports_environments": ["paper", "live"],
    },
    "polygon": {
        "display_name": "Polygon.io",
        "credential_kind": "api_key",
        "payload_fields": [
            {"name": "api_key", "label": "API Key", "secret": True},
        ],
        "meta_fields": [],
        "supports_environments": ["live"],
    },
    "interactive_brokers": {
        "display_name": "Interactive Brokers",
        "credential_kind": "basic_auth",
        "payload_fields": [
            {"name": "username", "label": "Username", "secret": False},
            {"name": "password", "label": "Password", "secret": True},
        ],
        "meta_fields": [
            {"name": "account_id", "label": "Account ID", "secret": False},
            {"name": "gateway_url", "label": "Gateway URL", "secret": False},
        ],
        "supports_environments": ["paper", "live"],
    },
    "tradier": {
        "display_name": "Tradier",
        "credential_kind": "api_key",
        "payload_fields": [
            {"name": "access_token", "label": "Access Token", "secret": True},
        ],
        "meta_fields": [
            {"name": "account_id", "label": "Account ID", "secret": False},
        ],
        "supports_environments": ["sandbox", "live"],
    },
    "binance": {
        "display_name": "Binance",
        "credential_kind": "api_key_pair",
        "payload_fields": [
            {"name": "api_key", "label": "API Key", "secret": True},
            {"name": "api_secret", "label": "API Secret", "secret": True},
        ],
        "meta_fields": [
            {"name": "region", "label": "Region (us / com)", "secret": False},
        ],
        "supports_environments": ["live", "sandbox"],
    },
    "schwab": {
        "display_name": "Charles Schwab",
        "credential_kind": "session_token",
        "payload_fields": [
            {"name": "session_token", "label": "Session Token", "secret": True},
        ],
        "meta_fields": [
            {"name": "account_id", "label": "Account ID", "secret": False},
        ],
        "supports_environments": ["paper", "live"],
    },
}


@router.get("/providers")
def list_providers() -> dict[str, Any]:
    """Return provider metadata for the frontend form."""
    return {
        "ok": True,
        "providers": [
            {"slug": slug, **meta} for slug, meta in sorted(_PROVIDER_METADATA.items())
        ],
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("")
def list_credentials(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    """List the caller's broker credentials (NEVER includes secret values)."""
    from sqlalchemy import desc, select

    from aqp.persistence.db import get_session
    from aqp.persistence.models_broker import BrokerCredential

    summaries: list[BrokerCredentialSummary] = []
    with get_session() as session:
        rows = (
            session.execute(
                select(BrokerCredential)
                .where(
                    BrokerCredential.owner_user_id == user.id,
                    BrokerCredential.revoked_at.is_(None),
                )
                .order_by(desc(BrokerCredential.created_at))
            )
            .scalars()
            .all()
        )
        for row in rows:
            summaries.append(
                BrokerCredentialSummary(
                    id=str(row.id),
                    provider=row.provider,
                    label=row.label,
                    credential_kind=row.credential_kind,
                    environment=row.environment,
                    is_active=bool(row.is_active),
                    last_used_at=row.last_used_at.isoformat() if row.last_used_at else None,
                    created_at=row.created_at.isoformat(),
                    meta=row.meta or {},
                )
            )
    return {"ok": True, "credentials": [s.model_dump() for s in summaries]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_credential(
    body: BrokerCredentialIn,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    """Create a new BYOK broker credential. Step-up MFA required.

    Encrypts the payload with envelope encryption (DEK wrapped by
    Vault Transit) and persists the ciphertext. The plaintext payload
    is dropped immediately after encryption — it NEVER touches a log
    line, an audit event, or the response body.
    """
    provider = body.provider.strip().lower()
    if not provider:
        raise HTTPException(400, "provider is required")
    if provider in _PROVIDER_METADATA:
        expected_kind = _PROVIDER_METADATA[provider]["credential_kind"]
        if body.credential_kind != expected_kind:
            raise HTTPException(
                400,
                f"provider {provider!r} requires credential_kind={expected_kind!r}",
            )
        # Reject payloads that don't include all required secret fields.
        for field in _PROVIDER_METADATA[provider]["payload_fields"]:
            name = field["name"]
            if not body.payload.get(name):
                raise HTTPException(400, f"payload field {name!r} is required for {provider}")

    # Reject any meta key whose value looks like a secret (operator
    # accidentally put the API key into meta instead of payload).
    for key in body.meta:
        if any(token in key.lower() for token in ("secret", "password", "key", "token")):
            raise HTTPException(
                400,
                f"meta field {key!r} looks like a secret; move it into ``payload``",
            )

    # Encrypt + persist.
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, "encryption library not available") from exc
    try:
        from aqp.credentials.vault_transit import encrypt as vault_encrypt
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, "vault transit not available") from exc
    from aqp.persistence.db import get_session
    from aqp.persistence.models_broker import BrokerCredential

    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    plaintext = json.dumps(body.payload, sort_keys=True).encode("utf-8")
    # We'll use the row id as additional authenticated data after
    # generating it so an attacker can't relocate ciphertext across rows.
    with get_session() as session:
        row = BrokerCredential(
            provider=provider,
            label=body.label.strip(),
            credential_kind=body.credential_kind,
            environment=body.environment,
            ciphertext=b"",  # populated below once we have an id
            nonce=nonce,
            wrapped_dek=b"",
            kek_id="",
            meta=dict(body.meta or {}),
        )
        # Apply tenancy stamping using the active context.
        try:
            from aqp.auth.deps import current_context as _cur_ctx  # noqa: F401
            from aqp.tenancy.runtime_context import get_runtime_context

            ctx = get_runtime_context()
            if ctx is not None:
                if not getattr(row, "owner_user_id", None):
                    row.owner_user_id = getattr(ctx, "user_id", None) or user.id
                if not getattr(row, "workspace_id", None):
                    row.workspace_id = getattr(ctx, "workspace_id", None)
                if not getattr(row, "organization_id", None):
                    row.organization_id = getattr(ctx, "org_id", None)
        except Exception:  # noqa: BLE001
            pass
        if not getattr(row, "owner_user_id", None):
            row.owner_user_id = user.id
        session.add(row)
        session.flush()  # populate row.id

        # Now run AEAD with the row id as AAD.
        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, plaintext, str(row.id).encode("ascii"))

        # Envelope-wrap the DEK via Vault Transit.
        wrapped = vault_encrypt(dek, tenant=str(row.organization_id or "default"))
        row.ciphertext = ciphertext
        row.wrapped_dek = wrapped.encode("ascii")
        # vault_encrypt returns "vault:v1:..." or "local:v1:..." — the
        # prefix identifies the KEK provider.
        row.kek_id = wrapped.split(":", 2)[0]
        session.flush()

        # Drop the plaintext + DEK in memory by overwriting before
        # returning. (CPython doesn't strictly zero them but this
        # frees the references for GC.)
        del plaintext
        del dek

        emit_audit_event(
            "broker_credential_created",
            user_id=user.id,
            organization_id=str(row.organization_id) if row.organization_id else None,
            workspace_id=str(row.workspace_id) if row.workspace_id else None,
            actor_user_id=user.id,
            event_category="account",
            severity="info",
            source="api",
            details={
                "credential_id": str(row.id),
                "provider": provider,
                "label": row.label,
                "environment": row.environment,
                "kek_id": row.kek_id,
                # NOTE: NEVER include payload fields here.
            },
        )

        return {
            "ok": True,
            "credential": BrokerCredentialSummary(
                id=str(row.id),
                provider=row.provider,
                label=row.label,
                credential_kind=row.credential_kind,
                environment=row.environment,
                is_active=True,
                last_used_at=None,
                created_at=row.created_at.isoformat(),
                meta=row.meta or {},
            ).model_dump(),
        }


@router.delete("/{credential_id}")
def revoke_credential(
    credential_id: str,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    """Soft-revoke a BYOK broker credential. Step-up MFA required."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_broker import BrokerCredential

    with get_session() as session:
        row = (
            session.query(BrokerCredential)
            .filter(
                BrokerCredential.id == credential_id,
                BrokerCredential.owner_user_id == user.id,
            )
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, "credential not found")
        if row.revoked_at is not None:
            return {"ok": True, "id": str(row.id), "revoked_at": row.revoked_at.isoformat()}
        row.revoked_at = datetime.utcnow()
        row.revoked_by_user_id = user.id
        row.is_active = False
        session.flush()
        emit_audit_event(
            "broker_credential_revoked",
            user_id=user.id,
            organization_id=str(row.organization_id) if row.organization_id else None,
            workspace_id=str(row.workspace_id) if row.workspace_id else None,
            actor_user_id=user.id,
            event_category="account",
            severity="info",
            source="api",
            details={"credential_id": str(row.id), "provider": row.provider},
        )
        return {"ok": True, "id": str(row.id), "revoked_at": row.revoked_at.isoformat()}


# ---------------------------------------------------------------------------
# Admin — switch the org's backend
# ---------------------------------------------------------------------------


@admin_router.put("/{org_id}/broker-backend")
def update_broker_backend(
    org_id: str,
    body: BrokerBackendUpdate,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    """Switch the org's broker-credential backend selector.

    Admin-only (verified by the route layer via the active context's
    membership role). Step-up MFA required.
    """
    from aqp.auth.user import user_can
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import Organization

    if not user_can(user, "admin", scope_kind="org", scope_id=org_id):
        raise HTTPException(403, "admin role on the org is required")

    with get_session() as session:
        row = session.query(Organization).filter(Organization.id == org_id).one_or_none()
        if row is None:
            raise HTTPException(404, "organization not found")
        previous = getattr(row, "broker_credential_backend", "local") or "local"
        row.broker_credential_backend = body.backend
        session.flush()
        emit_audit_event(
            "broker_backend_changed",
            user_id=user.id,
            organization_id=org_id,
            actor_user_id=user.id,
            event_category="account",
            severity="warning",
            source="api",
            details={
                "previous": previous,
                "new": body.backend,
            },
        )
        return {"ok": True, "organization_id": org_id, "backend": body.backend}


__all__ = ["admin_router", "router"]
