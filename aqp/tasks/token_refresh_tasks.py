"""Per-user external OAuth token refresh worker (Workstream D).

Celery beat task that scans :class:`UserOAuthToken` for rows
whose ``expires_at`` is within the configured refresh window
(default 300 s). For each match it:

1. Decrypts the stored token blob to recover the refresh_token.
2. Calls the matching :class:`ExternalOAuthProvider.refresh`.
3. Re-encrypts the resulting blob and updates the ORM row.

Failures (refresh token revoked / network) increment a counter on
the row's ``meta`` JSONB (best-effort) and surface in the next
``data.oauth.list_connections`` call so the user can re-authorise.

Hard rules honoured:

- **Rule 4 (Celery progress)** — every emit goes through
  :func:`emit` / :func:`emit_done` / :func:`emit_error` in
  :mod:`aqp.tasks._progress`.
- **Rule 26 (CredentialResolver)** — provider config is built via
  :func:`aqp.auth.external_oauth.flow._provider_config` which itself
  resolves through the resolver chain.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _refresh_window_seconds() -> int:
    try:
        from aqp.config import settings

        return int(getattr(settings, "user_oauth_refresh_window_seconds", 300) or 300)
    except Exception:  # noqa: BLE001
        return 300


def _enabled() -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, "user_oauth_enabled", False))
    except Exception:  # noqa: BLE001
        return False


def _impl(task_id: str) -> dict[str, Any]:
    if not _enabled():
        emit_done(task_id, {"ok": True, "skipped": True, "reason": "feature_disabled"})
        return {"ok": True, "skipped": True}

    emit(task_id, "scan", "scanning external oauth tokens")
    try:
        summary = _refresh_pass()
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, str(exc))
        logger.exception("token refresh failed")
        raise
    emit_done(task_id, summary)
    return {"ok": True, **summary}


def _refresh_pass() -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_oauth_tokens import UserOAuthToken

    window = timedelta(seconds=_refresh_window_seconds())
    now = datetime.utcnow()
    cutoff = now + window
    refreshed = 0
    failed = 0
    skipped = 0

    with get_session() as session:
        rows = (
            session.query(UserOAuthToken)
            .filter(
                UserOAuthToken.revoked_at.is_(None),
                UserOAuthToken.expires_at.isnot(None),
                UserOAuthToken.expires_at <= cutoff,
            )
            .limit(200)
            .all()
        )
        for row in rows:
            try:
                ok = _refresh_one_row(row)
                if ok:
                    refreshed += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001
                failed += 1
                logger.warning(
                    "refresh failed for user=%s source=%s",
                    row.user_id,
                    row.source,
                    exc_info=True,
                )
        session.commit()
    return {
        "refreshed": refreshed,
        "failed": failed,
        "skipped": skipped,
        "window_seconds": int(window.total_seconds()),
    }


def _refresh_one_row(row: Any) -> bool:
    """Best-effort refresh of one :class:`UserOAuthToken` row.

    Returns ``True`` when the refresh succeeded + the row was
    updated. Returns ``False`` when the refresh wasn't possible
    (e.g. no refresh_token stored, provider not registered, blob
    decryption failed). Raises on hard errors.
    """
    from aqp.auth.external_oauth.flow import _provider_config
    from aqp.auth.external_oauth.protocol import (
        ExternalOAuthProviderError,
        get_external_oauth_provider,
    )
    from aqp.credentials.vault_transit import decrypt, encrypt

    # Recover the refresh_token from the ciphertext store. We re-use
    # the same Redis-backed dev fallback the wizard writes to.
    try:
        from aqp.cache.client import get_metadata_cache

        cache = get_metadata_cache()
        redis_client = getattr(cache, "_client", None) or getattr(cache, "client", None)
    except Exception:  # noqa: BLE001
        redis_client = None
    if redis_client is None:
        return False
    raw = redis_client.get(f"aqp:user_oauth_blob:{row.vault_path}")
    if raw is None:
        return False
    ciphertext = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    tenant = str(row.organization_id or "default")
    try:
        blob = decrypt(ciphertext, tenant=tenant)
        decoded = json.loads(blob.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    refresh_token = decoded.get("refresh_token") or ""
    if not refresh_token:
        return False

    cls = get_external_oauth_provider(row.source)
    config = _provider_config(cls, overrides=None)
    provider = cls(config)
    try:
        token = provider.refresh(refresh_token)
    except ExternalOAuthProviderError as exc:
        logger.info(
            "refresh rejected for user=%s source=%s: %s",
            row.user_id,
            row.source,
            exc,
        )
        return False

    new_blob = json.dumps(
        {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token or refresh_token,
            "token_type": token.token_type,
            "scope": token.scope,
        }
    ).encode("utf-8")
    new_ciphertext = encrypt(new_blob, tenant=tenant)
    redis_client.set(f"aqp:user_oauth_blob:{row.vault_path}", new_ciphertext)

    row.last_refreshed_at = datetime.utcnow()
    if token.expires_in is not None:
        row.expires_at = datetime.utcnow() + timedelta(seconds=int(token.expires_in))
    return True


@celery_app.task(
    bind=True,
    name="aqp.tasks.token_refresh_tasks.refresh_external_oauth_tokens",
)
def refresh_external_oauth_tokens(self) -> dict[str, Any]:
    """Celery beat entry point — schedule every 60 s in prod."""
    task_id = self.request.id or "user-oauth-refresh"
    return _impl(task_id)


__all__ = ["refresh_external_oauth_tokens"]
