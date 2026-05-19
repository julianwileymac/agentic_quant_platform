"""WebSocket authentication — first-frame Bearer token protocol.

Phase 3a of the AQP control-plane maturation. Browsers cannot set
custom HTTP headers on the ``new WebSocket(...)`` handshake, which is
why most of AQP's existing WS routes call ``await ws.accept()`` without
any auth dependency. This module closes that gap with a simple
first-frame protocol:

1. Client opens the WS connection.
2. Server calls ``await websocket.accept()``.
3. Server calls :meth:`WebSocketAuthenticator.authenticate(ws)` which
   waits for the first JSON frame.
4. Client sends ``{"type": "auth", "token": "<bearer JWT>", ...}`` as
   the first frame. Optional context override fields:
   ``workspace_id``, ``project_id``, ``lab_id``.
5. Server validates the token via the existing
   :func:`aqp.auth.oidc.validate_jwt` (provider-agnostic, works with
   Auth0 / generic OIDC / mock / MSAL Entra) and builds a
   :class:`aqp.auth.context.RequestContext`.
6. Server responds with
   ``{"type": "auth_ok", "user_id": "...", "tenant_id": "...", "scopes": [...]}``
   and binds the context for the duration of the connection.

Failure modes (WebSocket close codes):

- ``4001`` — protocol error (malformed first frame, missing ``type`` /
  ``token``, or auth frame did not arrive within
  :data:`_AUTH_FRAME_TIMEOUT_SECONDS`).
- ``4003`` — invalid / expired token (signature failure, audience
  mismatch, ``exp`` past).
- ``4008`` — insufficient scope (caller required a scope the token
  didn't grant; returned by :meth:`require_ws_scope`).

The authenticator is feature-flagged via
``settings.ws_auth_required`` so the legacy "no first-frame auth" path
keeps working for one release cycle while the frontend cuts over.
When the flag is ``False`` (default in dev), an unauthenticated WS
connection silently degrades to the local-first default user, mirror-
ing the HTTP path's ``current_user`` fallback.

Usage example::

    from aqp.auth.ws import ws_authenticator

    @router.websocket("/live/stream/{channel_id}")
    async def stream(channel_id: str, ws: WebSocket):
        await ws.accept()
        ctx = await ws_authenticator.authenticate(ws)
        if ctx is None:
            return  # authenticator already closed the socket
        # ... use ctx.user_id, ctx.workspace_id, ctx.scopes ...
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Final

from fastapi import WebSocket, WebSocketDisconnect, status

from aqp.auth.context import RequestContext, default_context
from aqp.auth.oidc import (
    InvalidTokenError,
    JWKSUnavailableError,
    OIDCError,
    validate_jwt,
)

logger = logging.getLogger(__name__)


# WebSocket close codes (RFC 6455 reserves 4000-4999 for application use).
WS_CLOSE_PROTOCOL_ERROR: Final[int] = 4001
WS_CLOSE_TOKEN_INVALID: Final[int] = 4003
WS_CLOSE_INSUFFICIENT_SCOPE: Final[int] = 4008
WS_CLOSE_INTERNAL_ERROR: Final[int] = 4500

_AUTH_FRAME_TIMEOUT_SECONDS: Final[float] = 5.0


# ---------------------------------------------------------------------------
# Authentication result
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WebSocketAuthResult:
    """Outcome of a successful WebSocket authentication.

    Carries the verified :class:`RequestContext`, the raw JWT claims
    (so route handlers can inspect provider-specific fields), and the
    set of scopes granted by the token. Use :meth:`require_scope` to
    enforce per-endpoint authorization on top of the connection-level
    auth.
    """

    context: RequestContext
    claims: dict[str, Any] = field(default_factory=dict)
    scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def user_id(self) -> str:
        return self.context.user_id

    @property
    def tenant_id(self) -> str | None:
        return self.context.org_id

    def has_scope(self, scope: str) -> bool:
        from aqp.auth.scopes import AQPScope

        return scope in self.scopes or AQPScope.PLATFORM_ADMIN in self.scopes

    async def require_scope(self, ws: WebSocket, scope: str) -> bool:
        """Close *ws* with code 4008 if *scope* is not granted.

        Returns ``True`` if the scope is granted (caller continues),
        ``False`` if the socket was closed (caller must return).
        """
        if self.has_scope(scope):
            return True
        try:
            await ws.send_json(
                {
                    "type": "auth_error",
                    "code": "insufficient_scope",
                    "required": scope,
                }
            )
        except Exception:  # noqa: BLE001
            pass
        await _safe_close(ws, WS_CLOSE_INSUFFICIENT_SCOPE, "insufficient_scope")
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_close(ws: WebSocket, code: int, reason: str) -> None:
    """Close *ws* without raising if it's already closed."""
    try:
        await ws.close(code=code, reason=reason)
    except Exception:  # noqa: BLE001
        pass


def _is_ws_auth_required() -> bool:
    """Read ``settings.ws_auth_required`` (default False during cutover)."""
    try:
        from aqp.config import settings

        return bool(getattr(settings, "ws_auth_required", False))
    except Exception:  # noqa: BLE001
        return False


def _scopes_from_claims(claims: dict[str, Any]) -> frozenset[str]:
    """Best-effort scope extraction (matches HTTP _granted_scopes_for)."""
    scopes: set[str] = set()
    raw = claims.get("scope")
    if isinstance(raw, str):
        scopes.update(raw.split())
    perms = claims.get("permissions")
    if isinstance(perms, list):
        scopes.update(str(s) for s in perms if isinstance(s, str))
    # AQP-namespaced ``scopes`` claim
    try:
        from aqp.config import settings

        ns = str(settings.auth_claims_namespace or "https://aqp.internal/")
        if not ns.endswith("/"):
            ns += "/"
        ns_scopes = claims.get(f"{ns}scopes")
        if isinstance(ns_scopes, list):
            scopes.update(str(s) for s in ns_scopes if isinstance(s, str))
        ns_roles = claims.get(f"{ns}roles")
        if isinstance(ns_roles, list):
            try:
                from aqp.auth.scopes import expand_role_canonical

                for role in ns_roles:
                    scopes.update(expand_role_canonical(str(role)))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return frozenset(scopes)


def _context_from_claims(
    claims: dict[str, Any], overrides: dict[str, Any]
) -> RequestContext:
    """Build a :class:`RequestContext` from JWT claims + first-frame overrides.

    The first-frame ``workspace_id`` / ``project_id`` / ``lab_id`` keys
    behave the same way the HTTP ``X-AQP-*`` headers do — they pin the
    active scope for the rest of the connection. We do NOT validate the
    user's membership here; that check lives downstream when a
    framework call asks for ``user_can(...)``.
    """
    user_id = str(claims.get("sub") or "")
    if not user_id:
        # Fall back to the local-first default if the token lacked a sub
        ctx = default_context()
    else:
        ctx = RequestContext(user_id=user_id)
    # Pull in tenancy fields the Auth0 sync emits (canonical namespace).
    try:
        from aqp.config import settings

        ns = str(settings.auth_claims_namespace or "https://aqp.internal/")
        if not ns.endswith("/"):
            ns += "/"
        for field_name, claim_key in (
            ("org_id", "org_id"),
            ("workspace_id", "workspace_id"),
            ("project_id", "project_id"),
            ("lab_id", "lab_id"),
        ):
            value = claims.get(f"{ns}{claim_key}") or claims.get(claim_key)
            if value:
                ctx = ctx.with_overrides(**{field_name: str(value)})
    except Exception:  # noqa: BLE001
        pass
    # First-frame overrides win over the JWT claims (mirrors HTTP
    # X-AQP-* headers).
    override_keys = ("workspace_id", "project_id", "lab_id", "experiment_id", "test_id")
    apply: dict[str, Any] = {}
    for key in override_keys:
        if key in overrides and overrides[key] is not None:
            apply[key] = str(overrides[key])
    if apply:
        ctx = ctx.with_overrides(**apply)
    return ctx


# ---------------------------------------------------------------------------
# WebSocketAuthenticator
# ---------------------------------------------------------------------------


class WebSocketAuthenticator:
    """First-frame token-validating authenticator for AQP WebSocket routes.

    Single instance lives at the module bottom (:data:`ws_authenticator`).
    Routes call ``ctx = await ws_authenticator.authenticate(websocket)``
    immediately after ``await websocket.accept()`` and before any other
    receive/send. The authenticator handles all close-code semantics
    so route code only needs to check for a falsy return.

    The authenticator is intentionally NOT a FastAPI ``Depends`` —
    Starlette's WebSocket dependency injection uses a separate
    machinery from HTTP routes and the dependency-cache semantics are
    surprising. Calling the authenticator imperatively from the route
    body is the documented pattern.
    """

    def __init__(self, *, timeout_seconds: float = _AUTH_FRAME_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    async def authenticate(
        self, ws: WebSocket
    ) -> WebSocketAuthResult | None:
        """Wait for the first auth frame, validate, and return the context.

        Returns ``None`` if authentication failed (in which case the
        socket has already been closed with the appropriate close code).
        Returns a :class:`WebSocketAuthResult` on success.

        When ``settings.ws_auth_required`` is ``False`` (the default
        during cutover), a connection that fails to deliver a valid
        auth frame is permitted to continue with the local-first
        default context. When the flag is ``True``, the socket is
        closed.
        """
        required = _is_ws_auth_required()
        try:
            raw = await asyncio.wait_for(
                ws.receive_text(), timeout=self._timeout_seconds
            )
        except asyncio.TimeoutError:
            if required:
                await _safe_close(ws, WS_CLOSE_PROTOCOL_ERROR, "auth_timeout")
                return None
            logger.debug("ws_auth: no first frame, falling back to default context")
            return self._fallback_result()
        except WebSocketDisconnect:
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws_auth: receive failed: %s", exc)
            await _safe_close(ws, WS_CLOSE_PROTOCOL_ERROR, "receive_failed")
            return None

        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            if required:
                await _safe_close(ws, WS_CLOSE_PROTOCOL_ERROR, "invalid_json")
                return None
            logger.debug("ws_auth: non-JSON first frame, falling back")
            return self._fallback_result()

        if not isinstance(frame, dict) or frame.get("type") != "auth":
            if required:
                await _safe_close(ws, WS_CLOSE_PROTOCOL_ERROR, "expected_auth_frame")
                return None
            logger.debug("ws_auth: not an auth frame, falling back")
            return self._fallback_result()

        token = frame.get("token")
        if not isinstance(token, str) or not token:
            if required:
                await _safe_close(ws, WS_CLOSE_PROTOCOL_ERROR, "missing_token")
                return None
            return self._fallback_result()

        # Validate the token through the same path the HTTP layer uses.
        try:
            claims = validate_jwt(token)
        except InvalidTokenError as exc:
            logger.info("ws_auth: invalid token (%s)", exc)
            await _safe_close(ws, WS_CLOSE_TOKEN_INVALID, "invalid_token")
            return None
        except JWKSUnavailableError as exc:
            logger.warning("ws_auth: JWKS unavailable (%s)", exc)
            await _safe_close(ws, WS_CLOSE_INTERNAL_ERROR, "jwks_unavailable")
            return None
        except OIDCError as exc:
            logger.warning("ws_auth: OIDC error (%s)", exc)
            await _safe_close(ws, WS_CLOSE_INTERNAL_ERROR, "oidc_error")
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws_auth: validate_jwt failed (%s)", exc)
            await _safe_close(ws, WS_CLOSE_TOKEN_INVALID, "token_validation_failed")
            return None

        scopes = _scopes_from_claims(claims)
        ctx = _context_from_claims(claims, frame)

        # ACK the client so it can begin streaming. A confirmation frame
        # before the route's own data frames keeps the protocol
        # explicit and lets the client switch from "connecting" to
        # "open" UI states.
        try:
            await ws.send_json(
                {
                    "type": "auth_ok",
                    "user_id": ctx.user_id,
                    "tenant_id": ctx.org_id,
                    "scopes": sorted(scopes),
                }
            )
        except Exception:  # noqa: BLE001
            # If we can't even send the ACK, the socket is already
            # going down; just return the context and let the route
            # discover the failure on its first send.
            pass

        return WebSocketAuthResult(context=ctx, claims=claims, scopes=scopes)

    def _fallback_result(self) -> WebSocketAuthResult:
        """Build a local-first default context for unauthenticated dev sessions.

        Only reached when ``settings.ws_auth_required`` is ``False``.
        """
        return WebSocketAuthResult(
            context=default_context(),
            claims={},
            scopes=frozenset({"data:read"}),
        )


# Module-level singleton — routes import this directly.
ws_authenticator = WebSocketAuthenticator()


__all__ = [
    "WebSocketAuthenticator",
    "WebSocketAuthResult",
    "WS_CLOSE_INSUFFICIENT_SCOPE",
    "WS_CLOSE_INTERNAL_ERROR",
    "WS_CLOSE_PROTOCOL_ERROR",
    "WS_CLOSE_TOKEN_INVALID",
    "ws_authenticator",
]
