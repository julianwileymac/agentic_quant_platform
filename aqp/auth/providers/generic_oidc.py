"""Generic OIDC provider — discovery + RP-initiated logout.

Works with any standards-compliant OIDC IdP (Keycloak, Authentik, Dex,
Okta, etc.). Auth0 has its own quirks (``/v2/logout`` instead of
``end_session_endpoint``, ``audience`` query param on authorize) and
gets its own subclass; everything else inherits from this one.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from aqp.auth.oidc_client import OidcHttpClient
from aqp.auth.providers.protocol import (
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    M2MTokenResult,
    TokenResponse,
)

logger = logging.getLogger(__name__)


class GenericOidcProvider(IdentityProvider):
    """Standards-compliant OIDC provider implementation."""

    provider_kind = "oidc"
    provider_alias = "GenericOidcProvider"

    def __init__(self, config: IdentityProviderConfig) -> None:
        super().__init__(config)
        self._client = OidcHttpClient(discovery_url=config.issuer)

    # ------------------------------------------------------------------
    # Discovery / JWKS
    # ------------------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        return self._client.discovery()

    def jwks(self) -> dict[str, Any]:
        return self._client.jwks()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str = "openid profile email offline_access",
        audience: str | None = None,
    ) -> str:
        return self._client.authorize_url(
            client_id=self.config.client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            scope=scope,
            audience=audience or self.config.audience or None,
            extra_params=self.config.extra_authorize_params or None,
        )

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        raw = self._client.exchange_code(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        return _to_token_response(raw)

    def refresh(self, refresh_token: str) -> TokenResponse:
        raw = self._client.refresh(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            refresh_token=refresh_token,
        )
        return _to_token_response(raw)

    # ------------------------------------------------------------------
    # Logout (RP-initiated)
    # ------------------------------------------------------------------

    def logout_url(
        self,
        *,
        return_to: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        meta = self.discovery()
        endpoint = str(meta.get("end_session_endpoint") or "").strip()
        if not endpoint:
            raise IdentityProviderError(
                "Generic OIDC provider has no end_session_endpoint in discovery"
            )
        params: dict[str, str] = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if return_to:
            params["post_logout_redirect_uri"] = return_to
        elif self.config.logout_callback:
            params["post_logout_redirect_uri"] = self.config.logout_callback
        if not params:
            return endpoint
        sep = "&" if "?" in endpoint else "?"
        return f"{endpoint}{sep}{urlencode(params)}"

    # ------------------------------------------------------------------
    # M2M
    # ------------------------------------------------------------------

    def m2m_token(
        self,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> M2MTokenResult:
        raw = self._client.client_credentials(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            audience=audience or self.config.audience or None,
            scope=scope,
        )
        access = str(raw.get("access_token") or "")
        if not access:
            raise IdentityProviderError("M2M token endpoint returned empty access_token")
        return M2MTokenResult(
            access_token=access,
            expires_in=int(raw.get("expires_in") or 0),
            token_type=str(raw.get("token_type") or "Bearer"),
            scope=str(raw.get("scope") or "") or None,
        )


def _to_token_response(raw: dict[str, Any]) -> TokenResponse:
    return TokenResponse(
        access_token=str(raw.get("access_token") or ""),
        id_token=str(raw.get("id_token") or "") or None,
        refresh_token=str(raw.get("refresh_token") or "") or None,
        token_type=str(raw.get("token_type") or "Bearer"),
        expires_in=int(raw.get("expires_in") or 0) or None,
        scope=str(raw.get("scope") or "") or None,
        raw=raw,
    )


__all__ = ["GenericOidcProvider"]
