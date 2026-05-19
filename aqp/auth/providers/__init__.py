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

# Import MsalEntraProvider so the IdentityProviderMeta metaclass
# auto-registers it. The import is wrapped in a try/except so the AQP
# package keeps installable when ``msal`` isn't in the environment
# (the [auth-msal] extra has the dep).
try:  # pragma: no cover - dep guard
    from aqp.auth.providers.msal_entra import MsalEntraProvider  # noqa: F401
except Exception:  # noqa: BLE001
    MsalEntraProvider = None  # type: ignore[assignment]

# Same pattern for CloudflareAccessProvider — PyJWT + httpx are both
# already AQP hard deps, but we keep the import lazy so an unrelated
# import error here doesn't break the auth bootstrap.
try:  # pragma: no cover - dep guard
    from aqp.auth.providers.cloudflare_access import (  # noqa: F401
        CloudflareAccessProvider,
        extract_cloudflare_access_claims,
    )
except Exception:  # noqa: BLE001
    CloudflareAccessProvider = None  # type: ignore[assignment]
    extract_cloudflare_access_claims = None  # type: ignore[assignment]

__all__ = [
    "Auth0Provider",
    "CloudflareAccessProvider",
    "GenericOidcProvider",
    "IDENTITY_PROVIDER_KIND",
    "IdentityProvider",
    "IdentityProviderConfig",
    "IdentityProviderError",
    "IdentityProviderMeta",
    "M2MTokenResult",
    "MockProvider",
    "MsalEntraProvider",
    "TokenResponse",
    "extract_cloudflare_access_claims",
    "get_active_provider",
    "list_provider_classes",
    "register_provider",
    "reset_active_provider",
]
