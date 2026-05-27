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
from aqp.auth.providers.aws_cognito import AwsCognitoProvider
from aqp.auth.providers.aws_iam_identity_center import AwsIamIdentityCenterProvider
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

# ---------------------------------------------------------------------------
# Workstream "Entra internal tenant" — token-issuer-aware provider
# selector. ``manage.aqp.fund`` mounts use ``select_provider_for_token``
# so JWTs minted by the AQP staff Entra tenant land in MSAL before any
# other provider; everything else falls through to the configured
# active provider (Auth0 / OIDC / Cognito).
#
# The lookup is deliberately tolerant: when the token can't be parsed
# we fall back to the active provider rather than raise, mirroring the
# bear-trap-free philosophy of the rest of the auth chain.
# ---------------------------------------------------------------------------


def _internal_msal_issuer() -> str:
    """Return the MSAL internal-tenant issuer URL or empty string."""
    try:
        from aqp.config import settings

        tenant_id = (settings.auth_msal_internal_tenant_id or "").strip()
    except Exception:  # noqa: BLE001 - defensive
        return ""
    if not tenant_id:
        return ""
    # ``v2.0`` endpoints are the canonical issuer for staff tokens.
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0"


def _decode_jwt_issuer(token: str) -> str:
    """Best-effort issuer extraction without verifying signatures."""
    if not token or token.count(".") != 2:
        return ""
    import base64
    import json

    try:
        payload_b64 = token.split(".", 2)[1]
        # JWTs are URL-safe base64, padding stripped.
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return str(payload.get("iss", ""))
    except Exception:  # noqa: BLE001 - corrupt tokens shouldn't 500 the request
        return ""


def select_provider_for_token(token: str) -> "IdentityProvider":
    """Return the IdentityProvider that should verify ``token``.

    Routing rules (Workstream "Entra internal tenant"):

    1. If ``settings.auth_msal_internal_tenant_id`` is set AND the
       token's ``iss`` matches the configured internal-tenant issuer,
       return ``MsalEntraProvider``.
    2. Otherwise fall back to :func:`get_active_provider`, which
       returns whichever provider matches ``settings.auth_provider``.

    The function NEVER raises on parse errors — a malformed token
    falls back to the active provider, which then rejects it normally.
    """
    expected_issuer = _internal_msal_issuer()
    if expected_issuer and MsalEntraProvider is not None:
        token_issuer = _decode_jwt_issuer(token)
        if token_issuer and token_issuer.rstrip("/") == expected_issuer.rstrip("/"):
            try:
                from aqp.auth.providers.protocol import IdentityProviderConfig
                from aqp.config import settings

                cfg = IdentityProviderConfig(
                    issuer=expected_issuer,
                    audience=str(settings.auth_msal_internal_audience or "").strip()
                    or str(getattr(settings, "auth_oidc_audience", "") or "").strip(),
                    client_id=str(settings.auth_msal_internal_app_id or "").strip(),
                    client_secret=str(getattr(settings, "auth_msal_client_secret", "") or "").strip(),
                    logout_callback=str(getattr(settings, "auth_logout_callback", "") or "").strip(),
                )
                return MsalEntraProvider(cfg)
            except Exception:  # noqa: BLE001 - never let the route 500
                pass
    return get_active_provider()


__all__ = [
    "Auth0Provider",
    "AwsCognitoProvider",
    "AwsIamIdentityCenterProvider",
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
    "select_provider_for_token",
]
