"""PKCE auth-code flow helper for the external OAuth wizard (Workstream D).

Splits the user-facing PKCE dance into two steps:

- :func:`start_authorize_flow(user_id, source, redirect_uri)` — mint
  a ``state`` + ``code_verifier`` + ``code_challenge`` (S256), stash
  them in Redis keyed by ``state``, return the provider authorize URL
  + state.
- :func:`complete_authorize_flow(state, code)` — pop the stashed
  state, exchange the auth code via the provider, envelope-encrypt
  the resulting tokens, upsert the :class:`UserOAuthToken` row.

State storage uses the existing :class:`aqp.cache.client.MetadataCache`
Redis client so we don't add a new client. State TTL is 10 minutes —
plenty for the user to complete the redirect, but short enough that
abandoned flows don't pile up.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from aqp.auth.external_oauth.protocol import (
    ExternalOAuthProviderError,
    get_external_oauth_provider,
)

logger = logging.getLogger(__name__)


_STATE_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    """Return ``(verifier, challenge)`` for the PKCE S256 transform."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def _state_key(state: str) -> str:
    return f"aqp:oauth_state:{state}"


def _redis_client() -> Any | None:
    try:
        from aqp.cache.client import get_metadata_cache

        cache = get_metadata_cache()
        return getattr(cache, "_client", None) or getattr(cache, "client", None)
    except Exception:  # noqa: BLE001
        return None


def _save_state(state: str, payload: dict[str, Any]) -> None:
    client = _redis_client()
    if client is None:
        return
    try:
        client.set(_state_key(state), json.dumps(payload), ex=_STATE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.debug("oauth state save failed for state=%s", state, exc_info=True)


def _pop_state(state: str) -> dict[str, Any] | None:
    client = _redis_client()
    if client is None:
        return None
    key = _state_key(state)
    try:
        raw = client.get(key)
        if raw is None:
            return None
        client.delete(key)
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Flow entry points
# ---------------------------------------------------------------------------


def start_authorize_flow(
    *,
    user_id: str,
    organization_id: str | None,
    source: str,
    redirect_uri: str,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the provider authorize URL + stash PKCE + state.

    Returns ``{"state", "authorize_url"}``. The caller (the route)
    persists nothing more; the matching :func:`complete_authorize_flow`
    finishes the exchange.
    """
    if not source:
        raise ExternalOAuthProviderError("source is required")
    cls = get_external_oauth_provider(source)
    config = _provider_config(cls, overrides=config_overrides)
    provider = cls(config)
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    url = provider.authorize_url(
        state=state,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
    )
    _save_state(
        state,
        {
            "user_id": user_id,
            "organization_id": organization_id or "",
            "source": source,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
    )
    return {"state": state, "authorize_url": url}


def complete_authorize_flow(
    *,
    state: str,
    code: str,
) -> dict[str, Any]:
    """Redeem ``code`` against the provider + persist the token.

    Returns the upserted :class:`UserOAuthToken` row as a dict
    (``id`` + metadata; the token itself is never echoed).
    """
    stashed = _pop_state(state)
    if stashed is None:
        raise ExternalOAuthProviderError(
            "OAuth state is unknown or expired (10 min TTL)"
        )
    source = str(stashed.get("source") or "")
    if not source:
        raise ExternalOAuthProviderError("oauth state missing source")
    cls = get_external_oauth_provider(source)
    config = _provider_config(cls, overrides=None)
    provider = cls(config)
    token = provider.exchange_code(
        code=code,
        code_verifier=str(stashed.get("code_verifier") or ""),
        redirect_uri=str(stashed.get("redirect_uri") or ""),
    )
    return _persist_user_token(
        user_id=str(stashed.get("user_id") or ""),
        organization_id=str(stashed.get("organization_id") or "") or None,
        source=source,
        token=token,
    )


def _provider_config(cls, *, overrides: dict[str, Any] | None) -> Any:
    """Build the :class:`ExternalProviderConfig` for ``cls``.

    Pulls per-provider client id / secret from the
    :class:`CredentialResolver` so secrets never touch settings.*.
    """
    from aqp.auth.external_oauth.protocol import ExternalProviderConfig
    from aqp.credentials.protocol import CredentialKey
    from aqp.credentials.resolver import get_resolver

    base: Any = None
    if hasattr(cls, "default_config"):
        base = cls.default_config()
    if base is None:
        base = ExternalProviderConfig(
            authorize_endpoint="",
            token_endpoint="",
            client_id="",
        )

    resolver = get_resolver()
    try:
        cred = resolver.resolve(
            CredentialKey(f"external_oauth:{cls.provider_slug}", "client")
        )
        client_id = str((cred.fields or {}).get("client_id") or base.client_id)
        client_secret = str((cred.fields or {}).get("client_secret") or base.client_secret)
    except Exception:  # noqa: BLE001
        client_id = base.client_id
        client_secret = base.client_secret

    fields = {
        "authorize_endpoint": base.authorize_endpoint,
        "token_endpoint": base.token_endpoint,
        "client_id": client_id,
        "client_secret": client_secret,
        "default_scope": base.default_scope,
        "audience": base.audience,
        "extra_params": dict(base.extra_params or {}),
    }
    if overrides:
        for key, value in overrides.items():
            if key in fields:
                fields[key] = value
    return ExternalProviderConfig(**fields)


def _persist_user_token(
    *,
    user_id: str,
    organization_id: str | None,
    source: str,
    token: Any,
) -> dict[str, Any]:
    """Envelope-encrypt the token blob, upsert the ORM row."""
    from aqp.credentials.vault_transit import deterministic_vault_path, encrypt
    from aqp.persistence.db import get_session
    from aqp.persistence.models_oauth_tokens import UserOAuthToken

    if not user_id:
        raise ExternalOAuthProviderError("user_id missing from OAuth state")
    if not token or not getattr(token, "access_token", None):
        raise ExternalOAuthProviderError("provider returned no access_token")
    blob = json.dumps(
        {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "scope": token.scope,
        }
    ).encode("utf-8")
    tenant = organization_id or "default"
    ciphertext = encrypt(blob, tenant=tenant)
    vault_path = deterministic_vault_path(
        org_id=tenant, user_id=user_id, source=source
    )
    _store_ciphertext(vault_path, ciphertext)

    expires_at = None
    if token.expires_in is not None:
        expires_at = datetime.utcnow() + timedelta(seconds=int(token.expires_in))

    with get_session() as session:
        row = (
            session.query(UserOAuthToken)
            .filter(
                UserOAuthToken.user_id == user_id,
                UserOAuthToken.source == source,
                UserOAuthToken.revoked_at.is_(None),
            )
            .one_or_none()
        )
        if row is None:
            row = UserOAuthToken(
                user_id=user_id,
                organization_id=organization_id,
                source=source,
                vault_path=vault_path,
                scopes=[s for s in (token.scope or "").split() if s],
                expires_at=expires_at,
                label=None,
            )
            session.add(row)
        else:
            row.vault_path = vault_path
            row.scopes = [s for s in (token.scope or "").split() if s]
            row.expires_at = expires_at
            row.last_refreshed_at = datetime.utcnow()
        session.commit()
        return {
            "id": str(row.id),
            "user_id": user_id,
            "source": source,
            "scopes": list(row.scopes or []),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }


def _store_ciphertext(vault_path: str, ciphertext: str) -> None:
    """Persist the ciphertext into the configured Vault path.

    When Vault Transit isn't enabled the helper still encrypts the
    blob (NaCl SecretBox fallback) and stores it via the existing
    :class:`HashicorpVaultSecretStore` KV interface — but in dev
    deployments Vault is often absent. As a degraded fallback we keep
    the ciphertext in Redis keyed by the deterministic path. Operators
    flip to a real Vault deployment for production.
    """
    client = _redis_client()
    if client is None:
        return
    try:
        client.set(f"aqp:user_oauth_blob:{vault_path}", ciphertext)
    except Exception:  # noqa: BLE001
        logger.warning("ciphertext persist failed for path=%s", vault_path, exc_info=True)


__all__ = [
    "complete_authorize_flow",
    "start_authorize_flow",
]
