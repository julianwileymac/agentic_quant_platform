"""Pluggable identity providers for AQP.

Every concrete provider subclasses :class:`IdentityProvider` and sets a
``provider_kind`` (``"auth0"``, ``"oidc"``, ``"mock"``); the
:class:`IdentityProviderMeta` metaclass auto-registers it via
:func:`aqp.core.registry.register` (kind ``"identity_provider"``) so the
diagnostics endpoint and the resolver layer can introspect the active
provider.

Resolution order:

1. :func:`get_active_provider` — returns the provider matching
   ``settings.auth_provider`` (``auth0`` / ``oidc`` / ``mock``).
2. ``mock`` is the safe default for tests + offline dev.

The provider is the seam Milestone 3 uses for both user authentication
(``login_url`` / ``exchange_code``) and machine-to-machine tokens
(``m2m_token``).
"""
from __future__ import annotations

from aqp.auth.providers.auth0 import Auth0Provider
from aqp.auth.providers.generic_oidc import GenericOidcProvider
from aqp.auth.providers.mock import MockProvider
from aqp.auth.providers.protocol import (
    IDENTITY_PROVIDER_KIND,
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    IdentityProviderMeta,
    M2MTokenResult,
    TokenResponse,
    get_active_provider,
    list_provider_classes,
    register_provider,
    reset_active_provider,
)

__all__ = [
    "Auth0Provider",
    "GenericOidcProvider",
    "IDENTITY_PROVIDER_KIND",
    "IdentityProvider",
    "IdentityProviderConfig",
    "IdentityProviderError",
    "IdentityProviderMeta",
    "M2MTokenResult",
    "MockProvider",
    "TokenResponse",
    "get_active_provider",
    "list_provider_classes",
    "register_provider",
    "reset_active_provider",
]
