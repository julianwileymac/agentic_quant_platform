"""GitHub OAuth2 external provider (Workstream D)."""
from __future__ import annotations

from aqp.auth.external_oauth.protocol import ExternalProviderConfig
from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider


class GitHubExternalOAuthProvider(GenericExternalOAuthProvider):
    """GitHub developer OAuth2 (https://docs.github.com/en/apps/oauth-apps)."""

    provider_slug = "github"
    provider_alias = "GitHubExternalOAuthProvider"
    display_name = "GitHub"
    default_scope = "read:user repo"

    @classmethod
    def default_config(cls, client_id: str = "", client_secret: str = "") -> ExternalProviderConfig:
        return ExternalProviderConfig(
            authorize_endpoint="https://github.com/login/oauth/authorize",
            token_endpoint="https://github.com/login/oauth/access_token",
            client_id=client_id,
            client_secret=client_secret,
            default_scope=cls.default_scope,
        )


__all__ = ["GitHubExternalOAuthProvider"]
