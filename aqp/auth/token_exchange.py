"""RFC 8693 Token Exchange — delegated agent tokens (AGENTS hard rule 54).

When :class:`aqp.agents.runtime.AgentRuntime` dispatches a tool call
against the Data MCP or Codebase MCP servers, the request must carry a
JWT that proves three things:

1. The agent identity (so audit rows attribute the action correctly).
2. The human user the agent is acting on behalf of (so RLS + ownership
   checks evaluate against the human's workspace / project, not the
   agent's M2M client).
3. A *narrowed* scope set that excludes anything the human user did not
   grant the agent (so a compromised agent can't escalate by reusing a
   wide-scope M2M token).

The standardised mechanism for this binding is OAuth 2.0 Token Exchange
(RFC 8693). Auth0 exposes it via the ``Custom Token Exchange Profile``
surface — the operator creates a Profile named ``aqp-agent-delegation``
in the Auth0 dashboard, the Profile body sets the ``act`` claim from
``event.transaction.subject_token_payload``, narrows audience and
scopes, and returns a fresh short-lived access token.

This module is the AQP-side broker: given the human's currently-valid
access token plus an *actor assertion* identifying the agent, it calls
Auth0's ``/oauth/token`` endpoint with
``grant_type=urn:ietf:params:oauth:grant-type:token-exchange`` and
caches the resulting delegated token until 30 seconds before expiry.

Wire-format the broker emits (per Auth0 Custom Token Exchange docs):

.. code-block:: text

    POST https://<tenant>/oauth/token
    Content-Type: application/x-www-form-urlencoded

    grant_type=urn:ietf:params:oauth:grant-type:token-exchange
    subject_token=<user_access_token>
    subject_token_type=urn:ietf:params:oauth:token-type:access_token
    actor_token=<agent_actor_assertion>
    actor_token_type=urn:ietf:params:oauth:token-type:jwt
    audience=<settings.auth_oidc_audience>
    scope=read:mcp:data write:mcp:data
    client_id=<settings.auth_agent_broker_client_id>
    client_secret=<resolved via CredentialResolver>
    subject_token_profile=aqp-agent-delegation

The matching Auth0 Action body (Custom Token Exchange Profile) sets
``act.sub = "agent|<client_id>"`` on the minted access token so the
MCP server's :func:`aqp.api.security.get_current_user` path picks up
the delegation chain and:

- :class:`aqp.auth.deps.current_user` resolves the human user from the
  preserved ``sub`` claim (so RLS + memberships work).
- :func:`aqp.api.security_stepup._coerce_amr` reads the act claim and
  flips ``Principal.actor_type="agent"`` + ``on_behalf_of_sub=<human>``
  for downstream audit emission.
- :func:`aqp.auth.audit.emit_audit_event` accepts ``on_behalf_of_*``
  so the ``security_audit_events`` row captures who-on-behalf-of-whom.

The broker is feature-flagged by ``settings.auth_agent_token_exchange_enabled``;
when disabled, :meth:`TokenExchangeBroker.mint_for_agent` returns
``None`` and the calling :class:`AgentRuntime` falls back to passing
the original user token (no delegation, broader scopes — the legacy
behaviour during rollout).

The broker MUST NOT be used for non-agent token exchanges. The Auth0
Custom Token Exchange Profile is named ``aqp-agent-delegation`` and
the Profile body enforces the ``act`` claim is always set; using it
for arbitrary token swaps would mis-attribute audit rows.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from aqp.config import settings
from aqp.credentials import CredentialKey, CredentialNotFoundError, get_resolver

logger = logging.getLogger(__name__)


# RFC 8693 grant + token type constants
GRANT_TYPE_TOKEN_EXCHANGE: str = "urn:ietf:params:oauth:grant-type:token-exchange"
TOKEN_TYPE_ACCESS_TOKEN: str = "urn:ietf:params:oauth:token-type:access_token"
TOKEN_TYPE_JWT: str = "urn:ietf:params:oauth:token-type:jwt"

# Auth0 Profile name (matches aqp_docs/auth0-setup.md). Operators MUST
# create this Profile in the Dashboard before enabling
# ``auth_agent_token_exchange_enabled=true``.
DEFAULT_PROFILE_NAME: str = "aqp-agent-delegation"

# Default narrow scope for agent → MCP calls. Wider scopes require the
# Auth0 Profile to explicitly allow them. New MCP servers extend this
# list by adding to the Profile + here in lockstep.
DEFAULT_AGENT_SCOPES: tuple[str, ...] = (
    "read:mcp:data",
    "write:mcp:data",
    "read:mcp:codebase",
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class TokenExchangeError(RuntimeError):
    """Raised when the broker cannot mint a delegated token.

    Always carries the Auth0 error code (``invalid_request`` /
    ``invalid_grant`` / ``access_denied``) as the first positional
    argument so callers can branch without parsing the message string.
    The full upstream payload is attached to ``upstream_payload``.
    """

    def __init__(
        self,
        code: str,
        description: str | None = None,
        *,
        upstream_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(description or code)
        self.code = code
        self.upstream_payload = upstream_payload or {}


@dataclass(frozen=True)
class DelegatedToken:
    """Result of a successful Token Exchange.

    ``access_token`` is the JWT the calling :class:`AgentRuntime`
    attaches to its MCP HTTP requests as ``Authorization: Bearer``.
    ``act_sub`` is the agent identity Auth0 stamped onto the token via
    the Profile body; ``on_behalf_of_sub`` is the original ``sub`` of
    the human user the agent represents.
    """

    access_token: str
    expires_at: float
    scope: str
    audience: str
    act_sub: str
    on_behalf_of_sub: str
    raw_response: dict[str, Any]

    @property
    def expires_in(self) -> int:
        return max(0, int(self.expires_at - time.time()))


@dataclass(frozen=True)
class _CacheKey:
    """Per-(human, agent, audience, scope, profile) cache key."""

    user_sub: str
    agent_sub: str
    audience: str
    scope_sorted: tuple[str, ...]
    profile: str


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------


class TokenExchangeBroker:
    """Mint + cache RFC 8693 delegated tokens for agent runtimes.

    Construction is dependency-light so unit tests can swap the http
    client and the resolver via constructor kwargs. Production callers
    should use :func:`get_token_exchange_broker` to share the
    process-wide singleton — the cache + the credential lookup are
    expensive enough that re-instantiating per-call is wasteful.
    """

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 8.0,
        skew_seconds: int = 30,
        min_ttl_seconds: int = 60,
    ) -> None:
        self._http = http_client
        self._owns_http = http_client is None
        self._timeout_seconds = timeout_seconds
        self._skew_seconds = skew_seconds
        self._min_ttl_seconds = min_ttl_seconds
        self._cache: dict[_CacheKey, DelegatedToken] = {}
        self._lock = threading.RLock()

    # -- public API ---------------------------------------------------------

    def is_enabled(self) -> bool:
        """True when the operator has flipped the feature flag on AND
        the broker has the minimum config to issue a request."""
        if not bool(getattr(settings, "auth_agent_token_exchange_enabled", False)):
            return False
        if not str(getattr(settings, "auth_oidc_issuer", "") or ""):
            return False
        if not str(getattr(settings, "auth_oidc_audience", "") or ""):
            return False
        if not str(getattr(settings, "auth_agent_broker_client_id", "") or ""):
            return False
        return True

    def mint_for_agent(
        self,
        *,
        user_access_token: str,
        agent_actor_token: str,
        agent_subject: str,
        user_subject: str,
        scopes: tuple[str, ...] | None = None,
        audience: str | None = None,
        profile: str | None = None,
        force_refresh: bool = False,
    ) -> DelegatedToken | None:
        """Return a cached or freshly minted delegated token.

        ``agent_actor_token`` is a short-lived JWT minted by the
        :class:`M2MTokenIssuer` for the ``aqp-agent-broker`` client.
        The Auth0 Custom Token Exchange Profile reads its ``sub``
        claim and copies it into the ``act.sub`` of the minted
        access token; the caller should never construct it manually.

        ``user_access_token`` is the human's currently-valid AQP API
        access token (the one carried on the originating HTTP request
        that spawned the agent).

        Returns ``None`` when the feature is off or the configuration
        is incomplete — the caller falls back to non-delegated mode.
        Raises :class:`TokenExchangeError` for explicit upstream
        failures (invalid grant, audience mismatch, scope rejection).
        """
        if not self.is_enabled():
            return None
        scope_tuple = tuple(s for s in (scopes or DEFAULT_AGENT_SCOPES) if s)
        target_audience = audience or str(settings.auth_oidc_audience)
        profile_name = profile or DEFAULT_PROFILE_NAME

        cache_key = _CacheKey(
            user_sub=user_subject,
            agent_sub=agent_subject,
            audience=target_audience,
            scope_sorted=tuple(sorted(scope_tuple)),
            profile=profile_name,
        )

        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        token = self._exchange(
            user_access_token=user_access_token,
            agent_actor_token=agent_actor_token,
            agent_subject=agent_subject,
            user_subject=user_subject,
            audience=target_audience,
            scopes=scope_tuple,
            profile=profile_name,
        )
        if token is not None:
            self._cache_put(cache_key, token)
        return token

    def invalidate(self, *, user_subject: str, agent_subject: str | None = None) -> int:
        """Drop cached tokens for a user (and optionally a specific agent).

        Used by the log-stream webhook when an Auth0 session revoke
        event fires: the human revoked their session, so every
        in-flight agent acting on their behalf MUST stop being able
        to mint fresh delegated tokens.
        """
        with self._lock:
            keys = [
                k
                for k in self._cache
                if k.user_sub == user_subject
                and (agent_subject is None or k.agent_sub == agent_subject)
            ]
            for k in keys:
                self._cache.pop(k, None)
            return len(keys)

    def close(self) -> None:
        """Release the owned httpx client (no-op when one was injected)."""
        if self._owns_http and self._http is not None:
            try:
                self._http.close()
            finally:
                self._http = None

    # -- internals ----------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self._timeout_seconds)
        return self._http

    def _cache_get(self, key: _CacheKey) -> DelegatedToken | None:
        with self._lock:
            token = self._cache.get(key)
        if token is None:
            return None
        if token.expires_at - self._skew_seconds <= time.time():
            with self._lock:
                self._cache.pop(key, None)
            return None
        return token

    def _cache_put(self, key: _CacheKey, token: DelegatedToken) -> None:
        with self._lock:
            self._cache[key] = token

    def _resolve_broker_secret(self) -> str:
        """Resolve the ``aqp-agent-broker`` client_secret via CredentialResolver.

        Falls back to the env-shaped setting for local-dev so a
        ``AQP_AUTH_AGENT_BROKER_CLIENT_SECRET=...`` keeps working.
        """
        try:
            cred = get_resolver().resolve(
                CredentialKey("auth_agent_broker", "client_secret"),
                default=None,
            )
            if cred is not None:
                value = cred.fields.get("client_secret") or cred.fields.get("secret")
                if isinstance(value, str) and value:
                    return value
        except CredentialNotFoundError:
            pass
        except Exception:  # pragma: no cover - resolver chain is best-effort
            logger.debug("CredentialResolver lookup for broker secret failed", exc_info=True)
        env_value = str(getattr(settings, "auth_agent_broker_client_secret", "") or "")
        return env_value

    def _token_endpoint(self) -> str:
        issuer = str(settings.auth_oidc_issuer).rstrip("/")
        return f"{issuer}/oauth/token"

    def _exchange(
        self,
        *,
        user_access_token: str,
        agent_actor_token: str,
        agent_subject: str,
        user_subject: str,
        audience: str,
        scopes: tuple[str, ...],
        profile: str,
    ) -> DelegatedToken | None:
        client_id = str(settings.auth_agent_broker_client_id)
        client_secret = self._resolve_broker_secret()
        if not client_secret:
            logger.warning(
                "TokenExchangeBroker: no client_secret resolved for "
                "auth_agent_broker — falling back to non-delegated mode"
            )
            return None
        body = {
            "grant_type": GRANT_TYPE_TOKEN_EXCHANGE,
            "subject_token": user_access_token,
            "subject_token_type": TOKEN_TYPE_ACCESS_TOKEN,
            "actor_token": agent_actor_token,
            "actor_token_type": TOKEN_TYPE_JWT,
            "audience": audience,
            "scope": " ".join(scopes),
            "client_id": client_id,
            "client_secret": client_secret,
            "subject_token_profile": profile,
        }
        endpoint = self._token_endpoint()
        try:
            response = self._client().post(
                endpoint,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except httpx.HTTPError as exc:
            # Transport failures are not raised so the caller can
            # gracefully degrade to non-delegated mode.
            logger.warning(
                "TokenExchangeBroker: transport failure (%s); falling back",
                exc.__class__.__name__,
            )
            return None

        if response.status_code != 200:
            payload: dict[str, Any]
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                payload = {"raw": response.text}
            code = str(payload.get("error") or "invalid_request")
            description = payload.get("error_description") or response.text or code
            # The AGENTS rule 22 + Management Engine credential-safety
            # rule forbids printing tokens. We log the upstream error
            # code + description ONLY — never the body field values
            # of the request.
            logger.warning(
                "TokenExchangeBroker rejected: code=%s description=%r",
                code,
                str(description)[:240],
            )
            raise TokenExchangeError(code, str(description), upstream_payload=payload)

        try:
            payload = response.json()
        except ValueError as exc:
            raise TokenExchangeError(
                "invalid_response",
                "Token Exchange returned non-JSON",
            ) from exc

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise TokenExchangeError(
                "invalid_response",
                "Token Exchange response missing access_token",
                upstream_payload=payload,
            )

        expires_in = payload.get("expires_in")
        try:
            expires_in_int = int(expires_in) if expires_in is not None else 300
        except (TypeError, ValueError):
            expires_in_int = 300
        expires_in_int = max(self._min_ttl_seconds, expires_in_int)

        ttl_ceiling = int(getattr(settings, "auth_agent_delegation_ttl_seconds", 300))
        expires_in_int = min(expires_in_int, ttl_ceiling)
        expires_at = time.time() + expires_in_int - self._skew_seconds

        scope = str(payload.get("scope") or " ".join(scopes))

        return DelegatedToken(
            access_token=access_token,
            expires_at=expires_at,
            scope=scope,
            audience=audience,
            act_sub=agent_subject,
            on_behalf_of_sub=user_subject,
            raw_response=payload,
        )


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_BROKER: TokenExchangeBroker | None = None
_BROKER_LOCK = threading.Lock()


def get_token_exchange_broker() -> TokenExchangeBroker:
    """Return the cached process-wide broker.

    Lazy + thread-safe. Tests can override by passing their own
    instance into the callers that need it — never reach into this
    module's globals.
    """
    global _BROKER
    if _BROKER is None:
        with _BROKER_LOCK:
            if _BROKER is None:
                _BROKER = TokenExchangeBroker()
    return _BROKER


def reset_token_exchange_broker() -> None:
    """Reset the singleton (for tests / rotation)."""
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is not None:
            try:
                _BROKER.close()
            finally:
                _BROKER = None


__all__ = [
    "DEFAULT_AGENT_SCOPES",
    "DEFAULT_PROFILE_NAME",
    "DelegatedToken",
    "GRANT_TYPE_TOKEN_EXCHANGE",
    "TOKEN_TYPE_ACCESS_TOKEN",
    "TOKEN_TYPE_JWT",
    "TokenExchangeBroker",
    "TokenExchangeError",
    "get_token_exchange_broker",
    "reset_token_exchange_broker",
]
