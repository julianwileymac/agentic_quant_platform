"""Per-user external OAuth2 token store (Workstream D).

Registers itself with :class:`CredentialResolver` at priority 5 — above
``M2MStore`` (priority 10) because a user-scoped credential MUST win
over the service-level M2M token whenever the resolver runs inside a
request that carries an authenticated user.

Resolution flow:

1. Caller invokes ``resolver.resolve(CredentialKey("github",
   "user_oauth"))`` from inside a request scope where the active
   :class:`RequestContext` carries a non-default ``user_id``.
2. The store looks the user's :class:`UserOAuthToken` row up by
   ``(user_id, source)``.
3. If found and not expired, the encrypted token is unwrapped via
   :mod:`aqp.credentials.vault_transit` and returned as a
   :class:`Credential` with fields ``{access_token, scopes, expires_at}``.
4. If the row is expired, the store returns ``None`` — the caller
   then either falls back to a different store or surfaces a
   "re-authorise this connection" message to the user.

The store NEVER fires the token-refresh flow itself. Refresh is a
background concern handled by
:mod:`aqp.tasks.token_refresh_tasks.refresh_external_oauth_tokens`.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.credentials.protocol import Credential, CredentialKey, SecretStore

logger = logging.getLogger(__name__)


PRIORITY_USER_OAUTH = 5
USER_OAUTH_PURPOSE = "user_oauth"


class UserOAuthTokenStore(SecretStore):
    """Resolves per-user external OAuth tokens through the existing chain."""

    store_kind = "user_oauth"
    store_priority = PRIORITY_USER_OAUTH

    def get(self, key: CredentialKey) -> Credential | None:
        if str(key.purpose) != USER_OAUTH_PURPOSE:
            return None
        source = str(key.service)
        if not source:
            return None
        user_id = _current_user_id()
        if not user_id:
            return None
        return _read_user_token(user_id=user_id, source=source)


def _current_user_id() -> str | None:
    """Best-effort lookup of the active user id from the runtime context."""
    try:
        from aqp.tenancy.runtime_context import get_runtime_context

        ctx = get_runtime_context()
        if ctx is None:
            return None
        return getattr(ctx, "user_id", None)
    except Exception:  # noqa: BLE001
        return None


def _read_user_token(*, user_id: str, source: str) -> Credential | None:
    """Read the active :class:`UserOAuthToken` row and unwrap the token."""
    try:
        from aqp.credentials.vault_transit import decrypt
        from aqp.persistence.db import get_session
        from aqp.persistence.models_oauth_tokens import UserOAuthToken
    except Exception:  # noqa: BLE001
        return None

    try:
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
                return None
            if row.expires_at is not None and row.expires_at <= datetime.utcnow():
                logger.info(
                    "UserOAuthTokenStore: expired token for user=%s source=%s",
                    user_id,
                    source,
                )
                return None
            tenant = str(row.organization_id or "default")
            # Encrypted blob lives at row.vault_path. The blob's
            # bytes are the JSON dict
            # ``{"access_token": "...", "refresh_token": "..."}``.
            try:
                from aqp.credentials.resolver import get_resolver

                inner = get_resolver().resolve(
                    CredentialKey(
                        service=f"oauth2_blob:{row.vault_path}",
                        purpose="ciphertext",
                    )
                )
                ciphertext = inner.fields.get("ciphertext", "") if inner.fields else ""
            except Exception:  # noqa: BLE001
                ciphertext = ""
            if not ciphertext:
                return None
            try:
                blob = decrypt(ciphertext, tenant=tenant)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "UserOAuthTokenStore: decrypt failed for user=%s source=%s",
                    user_id,
                    source,
                )
                return None
            import json

            try:
                decoded = json.loads(blob.decode("utf-8"))
            except Exception:  # noqa: BLE001
                return None
            fields: dict[str, Any] = {
                "access_token": str(decoded.get("access_token") or ""),
                "token_type": str(decoded.get("token_type") or "Bearer"),
                "scopes": list(row.scopes or []),
            }
            if row.expires_at is not None:
                fields["expires_at"] = row.expires_at.isoformat()
            return Credential(
                fields=fields,
                source="user_oauth",
                ttl_seconds=_ttl_seconds_until(row.expires_at),
            )
    except Exception:  # noqa: BLE001
        logger.debug(
            "UserOAuthTokenStore.get failed for user=%s source=%s",
            user_id,
            source,
            exc_info=True,
        )
        return None


def _ttl_seconds_until(expires_at: datetime | None) -> int | None:
    if expires_at is None:
        return None
    delta = (expires_at - datetime.utcnow()).total_seconds()
    return max(0, int(delta))


def install_user_oauth_store() -> None:
    """Add the :class:`UserOAuthTokenStore` to the resolver singleton.

    Idempotent; safe to call multiple times. Called from
    :func:`aqp.credentials.resolver._build_default_resolver` when
    ``AQP_USER_OAUTH_ENABLED=true``.
    """
    from aqp.credentials.resolver import get_resolver

    resolver = get_resolver()
    for existing in resolver.stores():
        if isinstance(existing, UserOAuthTokenStore):
            return
    resolver.add_store(UserOAuthTokenStore())


__all__ = [
    "PRIORITY_USER_OAUTH",
    "USER_OAUTH_PURPOSE",
    "UserOAuthTokenStore",
    "install_user_oauth_store",
]
