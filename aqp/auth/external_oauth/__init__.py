"""Per-user external OAuth providers (Workstream D).

This package is the sibling of :mod:`aqp.auth.providers` (which
handles AQP's *own* IdP for user login). Where that one handles
"Auth0 / Entra signing the user into AQP", THIS one handles "the user
authorising AQP to call Bloomberg / Refinitiv / GitHub / FRED on
their behalf".

Public surface:

- :class:`ExternalOAuthProvider` — ABC + self-registering metaclass.
- :func:`list_external_oauth_providers` — registry walk.
- :func:`get_external_oauth_provider(slug)` — lookup helper.
- :mod:`aqp.auth.external_oauth.flow` — :func:`start_authorize_flow`
  + :func:`complete_authorize_flow` (the PKCE auth-code dance).
"""
from __future__ import annotations

from aqp.auth.external_oauth.protocol import (
    EXTERNAL_OAUTH_PROVIDER_KIND,
    ExternalOAuthProvider,
    ExternalOAuthProviderError,
    ExternalOAuthProviderMeta,
    ExternalProviderConfig,
    ExternalTokenResponse,
    get_external_oauth_provider,
    list_external_oauth_providers,
)
# Force-import the concrete providers package so the metaclass has had
# a chance to register them before any caller goes looking.
from aqp.auth.external_oauth import providers as _providers  # noqa: F401  (side-effects)

__all__ = [
    "EXTERNAL_OAUTH_PROVIDER_KIND",
    "ExternalOAuthProvider",
    "ExternalOAuthProviderError",
    "ExternalOAuthProviderMeta",
    "ExternalProviderConfig",
    "ExternalTokenResponse",
    "get_external_oauth_provider",
    "list_external_oauth_providers",
]
