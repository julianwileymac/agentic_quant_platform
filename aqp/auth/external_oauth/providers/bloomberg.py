"""Bloomberg Terminal / EAP OAuth2 provider (Workstream D).

Bloomberg's developer auth surface is gated; this provider exists so
the AQP wizard can show "Bloomberg" as a connection option and so
the credential resolver chain has a stable place to land the
encrypted token blob once a user authorises. Operators wire the
actual endpoints via env / config — Bloomberg's auth URLs are
tenant-specific.
"""
from __future__ import annotations

from aqp.auth.external_oauth.protocol import ExternalProviderConfig
from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider


class BloombergExternalOAuthProvider(GenericExternalOAuthProvider):
    """Bloomberg EAP / Terminal OAuth2."""

    provider_slug = "bloomberg"
    provider_alias = "BloombergExternalOAuthProvider"
    display_name = "Bloomberg"
    default_scope = "eap:read marketdata:read"

    @classmethod
    def default_config(cls, client_id: str = "", client_secret: str = "") -> ExternalProviderConfig:
        return ExternalProviderConfig(
            authorize_endpoint="",  # tenant-specific; operator overrides
            token_endpoint="",
            client_id=client_id,
            client_secret=client_secret,
            default_scope=cls.default_scope,
        )


__all__ = ["BloombergExternalOAuthProvider"]
