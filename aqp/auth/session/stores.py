"""Concrete :class:`StateStore` / :class:`TransactionStore` implementations.

Two backends:

- :class:`EncryptedCookieStateStore` — payload lives entirely inside a
  JWE cookie, encrypted with :mod:`aqp.auth.session.crypto`. The
  resolver layer never sees a session id; the store *is* the cookie.
  Choose this for the local-first / dev path.
- :class:`RedisStateStore` — payload lives in Redis under
  ``aqp:session:<id>``; the cookie carries only the session id.
  Choose this when the session payload exceeds the 4KB cookie limit
  or you want server-side revocation.

Both implementations expose the upstream
``set(identifier, payload, **options)`` /
``get(identifier, **options)`` /
``delete(identifier, **options)`` shape.
"""
from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any

from aqp.auth.session.crypto import decrypt_payload, encrypt_payload
from aqp.auth.session.protocol import StateStore, TransactionStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Encrypted cookie
# ---------------------------------------------------------------------------


class EncryptedCookieStateStore(StateStore):
    """Self-contained encrypted-cookie session store.

    ``set`` returns the JWE-serialised payload; ``get`` decrypts it.
    The framework adapter (FastAPI / Starlette) is responsible for
    actually setting / reading the cookie via ``store_options``:

    .. code-block:: python

        token = store.set("session-id", payload)  # writes to cookie
        # ``response.set_cookie("aqp_session", token)`` -- handled by route

    Identifier-as-salt: each session uses ``identifier`` as the HKDF
    salt so leaking one user's key does not weaken another's cookies.
    """

    def __init__(self, *, secret: str, cookie_name: str = "aqp_session") -> None:
        if not secret:
            raise ValueError("EncryptedCookieStateStore requires a non-empty secret")
        self._secret = secret
        self.cookie_name = cookie_name

    def set(self, identifier: str, payload: dict[str, Any], **_options: Any) -> str:
        return encrypt_payload(payload, self._secret, identifier)

    def get(self, identifier: str, **options: Any) -> dict[str, Any] | None:
        token = options.get("token") or ""
        if not token:
            return None
        try:
            return decrypt_payload(token, self._secret, identifier)
        except Exception as exc:  # noqa: BLE001 - any tamper / wrong-secret error
            logger.debug("EncryptedCookieStateStore decrypt failed: %s", exc)
            return None

    def delete(self, identifier: str, **_options: Any) -> None:
        # Cookie removal happens in the response helper; nothing to do
        # at the store layer for a stateless cookie payload.
        return None


class EncryptedCookieTransactionStore(EncryptedCookieStateStore, TransactionStore):
    """Reuse :class:`EncryptedCookieStateStore` for short-lived txn payloads."""

    def __init__(self, *, secret: str, cookie_name: str = "aqp_login_tx") -> None:
        super().__init__(secret=secret, cookie_name=cookie_name)


# ---------------------------------------------------------------------------
# Redis-backed
# ---------------------------------------------------------------------------


class RedisStateStore(StateStore):
    """Redis-backed session store, JSON payload at ``<prefix>:<id>``."""

    def __init__(
        self,
        *,
        redis_client: Any,
        prefix: str = "aqp:session",
        ttl_seconds: int = 60 * 60 * 24,
    ) -> None:
        if redis_client is None:
            raise ValueError("RedisStateStore requires a redis client")
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")
        self._ttl = max(60, int(ttl_seconds))

    def _key(self, identifier: str) -> str:
        return f"{self._prefix}:{identifier}"

    def set(self, identifier: str, payload: dict[str, Any], **_options: Any) -> None:
        body = json.dumps(payload, default=str)
        self._redis.set(self._key(identifier), body, ex=self._ttl)

    def get(self, identifier: str, **_options: Any) -> dict[str, Any] | None:
        raw = self._redis.get(self._key(identifier))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            logger.warning("RedisStateStore: corrupt payload at %s", self._key(identifier))
            return None

    def delete(self, identifier: str, **_options: Any) -> None:
        with contextlib.suppress(Exception):
            self._redis.delete(self._key(identifier))


class RedisTransactionStore(RedisStateStore, TransactionStore):
    """Same Redis-backed surface, scoped under a different prefix + shorter TTL."""

    def __init__(
        self,
        *,
        redis_client: Any,
        prefix: str = "aqp:login_tx",
        ttl_seconds: int = 600,
    ) -> None:
        super().__init__(
            redis_client=redis_client, prefix=prefix, ttl_seconds=ttl_seconds
        )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def session_payload_from_tokens(
    *,
    user_claims: dict[str, Any],
    access_token: str,
    id_token: str | None,
    refresh_token: str | None,
    audience: str,
    expires_in: int | None,
    scope: str | None,
) -> dict[str, Any]:
    """Shape the StateData-like payload the cookie / Redis store holds."""
    expires_at = int(time.time()) + int(expires_in or 0)
    return {
        "user": user_claims or {},
        "id_token": id_token,
        "refresh_token": refresh_token,
        "token_sets": [
            {
                "audience": audience,
                "access_token": access_token,
                "scope": scope,
                "expires_at": expires_at,
            }
        ],
        "internal": {
            "sid": str(user_claims.get("sid") or "") if isinstance(user_claims, dict) else "",
            "created_at": int(time.time()),
        },
    }


__all__ = [
    "EncryptedCookieStateStore",
    "EncryptedCookieTransactionStore",
    "RedisStateStore",
    "RedisTransactionStore",
    "session_payload_from_tokens",
]
