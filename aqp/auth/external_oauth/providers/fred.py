"""FRED (St Louis Fed) external provider (Workstream D).

FRED uses an API-key model rather than OAuth, but we still expose a
provider entry so the frontend wizard can list it and the user can
register their API key through the same UX. The "authorize" flow for
FRED is a no-op redirect that immediately returns the user-supplied
key wrapped as if it were an OAuth token.
"""
from __future__ import annotations

from aqp.auth.external_oauth.protocol import ExternalProviderConfig
from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider


class FredExternalOAuthProvider(GenericExternalOAuthProvider):
    """FRED API-key wrapper masquerading as OAuth2."""

    provider_slug = "fred"
    provider_alias = "FredExternalOAuthProvider"
    display_name = "FRED (St Louis Fed)"
    default_scope = ""

    @classmethod
    def default_config(cls, client_id: str = "", client_secret: str = "") -> ExternalProviderConfig:
        # FRED has no OAuth endpoints — the operator wires this up via
        # a custom-defined endpoint pair in their AQP config when they
        # want to use the unified credential path.
        return ExternalProviderConfig(
            authorize_endpoint="",
            token_endpoint="",
            client_id=client_id,
            client_secret=client_secret,
            default_scope="",
        )


__all__ = ["FredExternalOAuthProvider"]
