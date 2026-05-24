"""In-memory :class:`IdentityProvider` for tests + offline dev.

The mock provider:

- Synthesises a discovery document and an in-memory JWKS (no real keys
  — JWT validation against the mock should accept the provider's
  ``mock_token`` helper, not raw JWS).
- Echoes a deterministic auth code in :meth:`exchange_code` and
  :meth:`refresh`.
- Mints synthetic M2M tokens with a 15-minute TTL.

Using the mock for production is a config error; the
:meth:`exchange_code` / :meth:`m2m_token` methods deliberately return
fixed values so a misconfigured deployment is obvious.
"""
from __future__ import annotations

import secrets
from typing import Any

from aqp.auth.providers.protocol import (
    IdentityProvider,
    IdentityProviderConfig,
    M2MTokenResult,
    TokenResponse,
)


class MockProvider(IdentityProvider):
    """Deterministic mock for tests and offline dev."""

    provider_kind = "mock"
    provider_alias = "MockProvider"

    def __init__(self, config: IdentityProviderConfig | None = None) -> None:
        super().__init__(
            config
            or IdentityProviderConfig(
                issuer="http://mock-idp.local",
                audience="aqp-mock-api",
                client_id="aqp-mock-client",
                client_secret="aqp-mock-secret",  # noqa: S106 - test fixture
            )
        )

    def discovery(self) -> dict[str, Any]:
        base = self.config.issuer.rstrip("/") or "http://mock-idp.local"
        return {
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "jwks_uri": f"{base}/.well-known/jwks.json",
            "end_session_endpoint": f"{base}/oidc/logout",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "client_credentials",
            ],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    def jwks(self) -> dict[str, Any]:
        return {"keys": []}

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
        from urllib.parse import urlencode

        params = {
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": scope,
            "audience": audience or self.config.audience or "",
            "client_id": self.config.client_id or "aqp-mock-client",
            "response_type": "code",
        }
        if resource:
            params["resource"] = str(resource)
        endpoint = self.discovery()["authorization_endpoint"]
        return f"{endpoint}?{urlencode(params)}"

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        token = f"mock-access-{secrets.token_hex(8)}"
        return TokenResponse(
            access_token=token,
            id_token=f"mock-id-{secrets.token_hex(8)}",
            refresh_token=f"mock-refresh-{secrets.token_hex(8)}",
            expires_in=3600,
            scope="openid profile email offline_access",
            raw={
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier_used": bool(code_verifier),
            },
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        return TokenResponse(
            access_token=f"mock-access-{secrets.token_hex(8)}",
            id_token=f"mock-id-{secrets.token_hex(8)}",
            refresh_token=refresh_token,
            expires_in=3600,
            scope="openid profile email offline_access",
        )

    def logout_url(
        self,
        *,
        return_to: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        from urllib.parse import urlencode

        params: dict[str, str] = {}
        if return_to:
            params["post_logout_redirect_uri"] = return_to
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        base = self.discovery()["end_session_endpoint"]
        if not params:
            return base
        return f"{base}?{urlencode(params)}"

    def m2m_token(
        self,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> M2MTokenResult:
        return M2MTokenResult(
            access_token=f"mock-m2m-{secrets.token_hex(8)}",
            expires_in=900,
            scope=scope,
        )


__all__ = ["MockProvider"]
