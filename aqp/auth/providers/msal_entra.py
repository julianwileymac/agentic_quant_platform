"""Microsoft Entra ID (formerly Azure AD) :class:`IdentityProvider`.

Wraps :class:`msal.ConfidentialClientApplication` from the official
``microsoft-authentication-library-for-python`` package (a.k.a. MSAL
Python). Mirrors :class:`aqp.auth.providers.auth0.Auth0Provider` so the
metaclass auto-registers it via :func:`aqp.core.registry.register` when
the class is imported.

Multi-tenant by default:

- ``authority`` defaults to ``https://login.microsoftonline.com/organizations``
  which accepts users from any Entra tenant (B2B / external enterprise
  clients).
- Pin to ``https://login.microsoftonline.com/{tenant_id}`` for
  single-tenant deployments.
- Use ``/common`` to additionally accept personal Microsoft accounts.

First-login provisioning maps the Entra ``tid`` (tenant id) claim to a
:class:`aqp.persistence.models_tenancy.Organization` row through the
:class:`aqp.persistence.models_terraform.EntraTenantLink` index. The
link is created in ``pending`` state on first sight of an unknown
tenant when ``settings.auth_msal_b2b_enabled`` is ``True``; an AQP
super-admin promotes it to ``active`` via the onboarding wizard. See
:func:`aqp.auth.user.provision_user_from_claims` for the call-site.

This module deliberately does NOT subclass :class:`GenericOidcProvider`
— MSAL maintains its own token cache and exposes the
``initiate_auth_code_flow`` / ``acquire_token_by_auth_code_flow`` pair
that we want to use directly so per-user PKCE / nonce state stays
consistent with the SPA's ``@azure/msal-react`` client.

Setup runbook: see [aqp_docs/docs/concepts/identity/msal-entra-setup.md](aqp_docs/docs/concepts/identity/msal-entra-setup.md).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from aqp.auth.providers.protocol import (
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    M2MTokenResult,
    TokenResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-process flow store
# ---------------------------------------------------------------------------


class _FlowStore:
    """Per-state cache for MSAL's ``initiate_auth_code_flow`` payload.

    MSAL emits a ``flow`` dict on ``initiate_auth_code_flow`` that
    encodes the PKCE verifier, nonce, scopes, and redirect-uri the
    matching ``acquire_token_by_auth_code_flow`` call needs to redeem
    the auth code. The dict MUST be stored per-user (keyed by the
    OAuth ``state`` parameter) — sharing it globally would crater the
    PKCE binding.

    The store is process-local on purpose: the AQP backend sees the
    same FastAPI worker for both the ``/auth/login`` redirect and the
    ``/auth/callback`` exchange because the SPA carries the ``state``
    back. For multi-worker deployments the session backend
    (:class:`aqp.auth.session.stores`) takes over and this in-memory
    map degrades to a best-effort hit.
    """

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ttl = max(60, int(ttl_seconds))

    def save(self, state: str, flow: dict[str, Any]) -> None:
        with self._lock:
            self._items[state] = (time.monotonic() + self._ttl, dict(flow))
            self._evict_expired_locked()

    def pop(self, state: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._items.pop(state, None)
            if row is None:
                return None
            expiry, flow = row
            if time.monotonic() > expiry:
                return None
            return flow

    def _evict_expired_locked(self) -> None:
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._items.items() if exp <= now]:
            self._items.pop(key, None)


_flow_store = _FlowStore()


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class MsalEntraProvider(IdentityProvider):
    """Microsoft Entra ID provider built on MSAL Python."""

    provider_kind = "msal_entra"
    provider_alias = "MsalEntraProvider"

    def __init__(self, config: IdentityProviderConfig) -> None:
        super().__init__(config)
        self._app: Any | None = None
        self._discovery_cache: tuple[float, dict[str, Any]] | None = None
        self._jwks_cache: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Lazy MSAL client construction
    # ------------------------------------------------------------------

    def _get_app(self) -> Any:
        """Return the lazily-constructed :class:`msal.ConfidentialClientApplication`.

        We construct lazily so a misconfigured deployment (empty
        client_id, missing client_secret) doesn't crash on import.
        Tests can also stub ``self._app`` directly.
        """
        if self._app is not None:
            return self._app
        try:
            import msal  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - dep guard
            raise IdentityProviderError(
                "msal is required for MsalEntraProvider; install with "
                "`pip install 'agentic-quant-platform[auth-msal]'` or "
                "`pip install msal`"
            ) from exc

        authority = (self.config.issuer or "").strip()
        if not authority:
            authority = "https://login.microsoftonline.com/organizations"

        client_id = (self.config.client_id or "").strip()
        if not client_id:
            raise IdentityProviderError(
                "MsalEntraProvider requires AQP_MSAL_CLIENT_ID / "
                "auth_oidc_client_id to be set"
            )

        client_credential: str | dict[str, Any] | None = None
        secret = (self.config.client_secret or "").strip()
        if secret:
            # MSAL accepts a plain string for the secret-based flow or a
            # dict shaped {"private_key": ..., "thumbprint": ...} for
            # certificate auth. We pick the string path here; cert-based
            # confidential clients can replace ``self._app`` post-init.
            client_credential = secret

        with self._lock:
            if self._app is None:
                self._app = msal.ConfidentialClientApplication(
                    client_id=client_id,
                    authority=authority,
                    client_credential=client_credential,
                )
        return self._app

    # ------------------------------------------------------------------
    # Discovery / JWKS
    # ------------------------------------------------------------------

    def _discovery_uri(self) -> str:
        authority = (self.config.issuer or "").rstrip("/")
        if not authority:
            authority = "https://login.microsoftonline.com/organizations"
        # Entra v2 discovery is always under /v2.0/.well-known/openid-configuration.
        if authority.endswith("/v2.0"):
            return f"{authority}/.well-known/openid-configuration"
        return f"{authority}/v2.0/.well-known/openid-configuration"

    def discovery(self) -> dict[str, Any]:
        """Return the cached Entra OIDC discovery document."""
        now = time.monotonic()
        cached = self._discovery_cache
        if cached is not None and now < cached[0]:
            return cached[1]
        uri = self._discovery_uri()
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(uri)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            if cached is not None:
                logger.warning(
                    "Entra discovery fetch failed (%s); serving cached doc past TTL",
                    exc,
                )
                return cached[1]
            raise IdentityProviderError(
                f"Could not fetch Entra discovery at {uri}: {exc}"
            ) from exc
        if not isinstance(payload, dict) or "issuer" not in payload:
            raise IdentityProviderError(
                f"Entra discovery at {uri} returned an unexpected payload"
            )
        with self._lock:
            self._discovery_cache = (now + 3600.0, payload)
        return payload

    def jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._jwks_cache
        if cached is not None and now < cached[0]:
            return cached[1]
        meta = self.discovery()
        jwks_uri = str(meta.get("jwks_uri") or "").strip()
        if not jwks_uri:
            raise IdentityProviderError(
                "Entra discovery is missing the jwks_uri claim"
            )
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(jwks_uri)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            if cached is not None:
                return cached[1]
            raise IdentityProviderError(
                f"Could not fetch Entra JWKS at {jwks_uri}: {exc}"
            ) from exc
        if not isinstance(payload, dict) or "keys" not in payload:
            raise IdentityProviderError(
                f"Entra JWKS at {jwks_uri} is not a valid JSON Web Key Set"
            )
        with self._lock:
            self._jwks_cache = (now + 3600.0, payload)
        return payload

    # ------------------------------------------------------------------
    # Auth code flow (PKCE)
    # ------------------------------------------------------------------

    def login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str = "openid profile email offline_access",
        audience: str | None = None,
        resource: str | None = None,
    ) -> str:
        """Return the Entra authorize URL via :meth:`initiate_auth_code_flow`.

        The ``code_challenge`` argument is accepted for API parity with
        the other providers but MSAL manages its own PKCE state inside
        the returned flow dict. The flow dict is stored under the
        provided ``state`` so the callback handler can resolve it.

        ``scope`` is split on whitespace. Entra protected-resource
        scopes (e.g. ``api://<app_id>/.default``) can be appended via
        the optional ``audience`` argument — when set, it is passed as
        an additional scope (Entra ignores the OAuth ``audience``
        query param the Auth0 path uses).

        ``resource`` (RFC 8707) is appended to ``data`` for Microsoft
        Entra: it accepts the parameter on v2.0 ``/oauth2/v2.0/authorize``
        but ignores it for the access-token audience binding (Entra
        uses scopes for that). We forward it for spec parity and so any
        downstream proxy honours the binding.
        """
        app = self._get_app()
        scopes = [s for s in (scope or "").split() if s]
        if audience:
            # Allow the caller to inject the API audience as an
            # additional scope. MSAL deduplicates internally.
            scopes.append(str(audience).strip())
        try:
            kwargs: dict[str, Any] = {
                "scopes": scopes,
                "redirect_uri": redirect_uri,
                "state": state,
            }
            if resource:
                kwargs["data"] = {"resource": str(resource)}
            flow = app.initiate_auth_code_flow(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise IdentityProviderError(
                f"MSAL initiate_auth_code_flow failed: {exc}"
            ) from exc
        if not isinstance(flow, dict) or "auth_uri" not in flow:
            raise IdentityProviderError(
                "MSAL initiate_auth_code_flow returned an unexpected payload"
            )
        _flow_store.save(state, flow)
        return str(flow["auth_uri"])

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        """Redeem the auth code via :meth:`acquire_token_by_auth_code_flow`.

        MSAL needs the original ``flow`` dict to decode the PKCE
        verifier + nonce — we pop it from the in-process store keyed
        by the ``state`` parameter. The ``state`` is encoded in the
        callback URL query string and threaded through the
        :class:`aqp.auth.session.stores` session by
        :mod:`aqp.api.routes.auth`.

        To stay compatible with the abstract ABC signature we accept
        ``code_verifier`` for parity (MSAL ignores it; the verifier is
        on the cached ``flow``). The flow lookup is keyed by the
        ``state`` value which we expect callers to plumb through via
        the ``flow_state`` extra on :class:`TokenResponse.raw`.
        """
        app = self._get_app()
        # The state is needed to look up the flow; callers (auth route)
        # pass it via ``code_verifier`` when there's no separate
        # plumbing. The mock and Auth0 providers don't need this, so
        # the protocol keeps the arg ABC-level neutral.
        state = code_verifier or ""
        flow = _flow_store.pop(state) if state else None
        if flow is None:
            raise IdentityProviderError(
                "MsalEntraProvider could not resolve auth_code_flow state. "
                "Make sure the SPA threaded the ``state`` value back through "
                "the callback and the AQP /auth/login + /auth/callback "
                "endpoints serialized it onto the session."
            )
        # MSAL expects the full query-string dict from the callback.
        # Tests can synthesise just {code, state} to validate; the
        # session route plumbs the full mapping.
        response_dict = {"code": code, "state": state}
        try:
            result = app.acquire_token_by_auth_code_flow(flow, response_dict)
        except Exception as exc:  # noqa: BLE001
            raise IdentityProviderError(
                f"MSAL acquire_token_by_auth_code_flow failed: {exc}"
            ) from exc
        if not isinstance(result, dict) or "access_token" not in result:
            err = (result or {}).get("error_description") or (result or {}).get("error")
            raise IdentityProviderError(
                f"MSAL token exchange returned no access_token: {err!r}"
            )
        return _to_token_response(result)

    def refresh(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token via :meth:`acquire_token_by_refresh_token`."""
        app = self._get_app()
        scopes = [s for s in (self.config.audience or "").split() if s] or [
            "openid",
            "profile",
            "email",
            "offline_access",
        ]
        try:
            result = app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)
        except Exception as exc:  # noqa: BLE001
            raise IdentityProviderError(
                f"MSAL acquire_token_by_refresh_token failed: {exc}"
            ) from exc
        if not isinstance(result, dict) or "access_token" not in result:
            err = (result or {}).get("error_description") or (result or {}).get("error")
            raise IdentityProviderError(
                f"MSAL refresh returned no access_token: {err!r}"
            )
        return _to_token_response(result)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout_url(
        self,
        *,
        return_to: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        """Entra v2 RP-initiated logout endpoint."""
        authority = (self.config.issuer or "").rstrip("/")
        if not authority:
            authority = "https://login.microsoftonline.com/organizations"
        # Entra logout endpoint lives under /oauth2/v2.0/logout. The
        # /organizations and /common authorities also support this.
        if authority.endswith("/v2.0"):
            base = f"{authority.rsplit('/v2.0', 1)[0]}/oauth2/v2.0/logout"
        else:
            base = f"{authority}/oauth2/v2.0/logout"
        params: dict[str, str] = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        target = return_to or self.config.logout_callback
        if target:
            params["post_logout_redirect_uri"] = target
        if not params:
            return base
        return f"{base}?{urlencode(params)}"

    # ------------------------------------------------------------------
    # Machine-to-machine (client_credentials)
    # ------------------------------------------------------------------

    def m2m_token(
        self,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> M2MTokenResult:
        """Mint a service-to-service token via :meth:`acquire_token_for_client`.

        Entra's client_credentials grant uses ``api://<app_id>/.default``
        style scopes (NOT the audience query param). When ``audience``
        is supplied we treat it as the resource indicator and request
        the matching ``.default`` scope.
        """
        app = self._get_app()
        scopes: list[str]
        if scope:
            scopes = [s for s in scope.split() if s]
        elif audience:
            aud = str(audience).strip()
            if aud.endswith("/.default"):
                scopes = [aud]
            else:
                scopes = [f"{aud.rstrip('/')}/.default"]
        elif self.config.audience:
            aud = str(self.config.audience).strip()
            if aud.endswith("/.default"):
                scopes = [aud]
            else:
                scopes = [f"{aud.rstrip('/')}/.default"]
        else:
            raise IdentityProviderError(
                "MsalEntraProvider.m2m_token requires either audience or scope"
            )
        try:
            result = app.acquire_token_for_client(scopes=scopes)
        except Exception as exc:  # noqa: BLE001
            raise IdentityProviderError(
                f"MSAL acquire_token_for_client failed: {exc}"
            ) from exc
        if not isinstance(result, dict) or "access_token" not in result:
            err = (result or {}).get("error_description") or (result or {}).get("error")
            raise IdentityProviderError(
                f"MSAL client-credentials returned no access_token: {err!r}"
            )
        return M2MTokenResult(
            access_token=str(result["access_token"]),
            expires_in=int(result.get("expires_in") or 0),
            token_type=str(result.get("token_type") or "Bearer"),
            scope=" ".join(scopes),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_token_response(raw: dict[str, Any]) -> TokenResponse:
    return TokenResponse(
        access_token=str(raw.get("access_token") or ""),
        id_token=str(raw.get("id_token") or "") or None,
        refresh_token=str(raw.get("refresh_token") or "") or None,
        token_type=str(raw.get("token_type") or "Bearer"),
        expires_in=int(raw.get("expires_in") or 0) or None,
        scope=str(raw.get("scope") or "") or None,
        raw=dict(raw),
    )


__all__ = ["MsalEntraProvider"]
