"""Auth0-specific :class:`IdentityProvider`.

Inherits from :class:`GenericOidcProvider` and overrides the two
behaviors that diverge from standard OIDC:

1. ``logout_url`` uses ``https://<tenant>/v2/logout?client_id=...&returnTo=...``
   (the standard OIDC ``end_session_endpoint`` is absent on Auth0).
2. ``login_url`` always passes the configured ``audience`` so the
   issued access tokens target the AQP API resource (Auth0-specific
   convention; harmless on generic OIDC but Auth0 needs it).
"""
from __future__ import annotations

from urllib.parse import urlencode

from aqp.auth.providers.generic_oidc import GenericOidcProvider
from aqp.auth.providers.protocol import IdentityProviderError


class Auth0Provider(GenericOidcProvider):
    """Auth0 tenant provider."""

    provider_kind = "auth0"
    provider_alias = "Auth0Provider"

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
        # Auth0 *requires* the audience query param to mint an access
        # token for a non-OIDC API; pass through whatever the caller
        # provided or fall back to the configured audience. The
        # ``resource`` argument (RFC 8707) propagates through the
        # generic-OIDC base so MCP clients can audience-bind tokens to
        # a specific MCP server URI per the 2025-11-25 spec.
        return super().login_url(
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            scope=scope,
            audience=audience or self.config.audience or None,
            resource=resource,
        )

    def logout_url(
        self,
        *,
        return_to: str | None = None,
        id_token_hint: str | None = None,
    ) -> str:
        issuer = (self.config.issuer or "").rstrip("/")
        if not issuer:
            raise IdentityProviderError("Auth0 provider has no configured issuer")
        params: dict[str, str] = {}
        if self.config.client_id:
            params["client_id"] = self.config.client_id
        if return_to:
            params["returnTo"] = return_to
        elif self.config.logout_callback:
            params["returnTo"] = self.config.logout_callback
        base = f"{issuer}/v2/logout"
        if not params:
            return base
        return f"{base}?{urlencode(params)}"


__all__ = ["Auth0Provider"]
