"""Refinitiv (LSEG) Data Platform OAuth2 provider (Workstream D)."""
from __future__ import annotations

from aqp.auth.external_oauth.protocol import ExternalProviderConfig
from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider


class RefinitivExternalOAuthProvider(GenericExternalOAuthProvider):
    """Refinitiv / LSEG Data Platform OAuth2."""

    provider_slug = "refinitiv"
    provider_alias = "RefinitivExternalOAuthProvider"
    display_name = "Refinitiv (LSEG)"
    default_scope = "trapi"

    @classmethod
    def default_config(cls, client_id: str = "", client_secret: str = "") -> ExternalProviderConfig:
        return ExternalProviderConfig(
            authorize_endpoint="https://api.refinitiv.com/auth/oauth2/v2/authorize",
            token_endpoint="https://api.refinitiv.com/auth/oauth2/v2/token",
            client_id=client_id,
            client_secret=client_secret,
            default_scope=cls.default_scope,
        )


__all__ = ["RefinitivExternalOAuthProvider"]
