"""Authentication primitives shared across the AQP planes.

- :mod:`aqp_platform_core.auth.jwt_validator` — JWKS-backed RS256 JWT validator.
- :mod:`aqp_platform_core.auth.claims` — canonical claim namespace constants.
- :mod:`aqp_platform_core.auth.rbac` — four-role scope grid.
- :mod:`aqp_platform_core.auth.resource_filter` — resource-scoped list filter
  enforced by every list endpoint in the control plane.
- :mod:`aqp_platform_core.auth.providers` — minimal identity provider
  shims (Microsoft Entra ID primary, Auth0 fallback).
- :mod:`aqp_platform_core.auth.m2m` — :class:`M2MTokenBroker` for
  admin -> CP and CP -> monolith machine-to-machine calls.

After the rule 27 + identity.mdc update Microsoft Entra ID is the
primary IdP. Use :func:`default_identity_provider_alias` to read
the configured default; Auth0 remains a registered fallback for the
B2C self-signup pool.
"""
from __future__ import annotations

import os

from aqp_platform_core.auth.claims import (
    CANONICAL_CLAIMS_NAMESPACE,
    LEGACY_CLAIMS_NAMESPACE,
    claim_key,
    extract_claim,
)
from aqp_platform_core.auth.jwt_validator import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
)
from aqp_platform_core.auth.m2m import (
    M2MBrokerError,
    M2MTokenBroker,
    M2MTokenBrokerConfig,
    broker_for_default_provider,
)
from aqp_platform_core.auth.providers import (
    IdentityProviderShim,
    IdentityProviderShimConfig,
    M2MGrant,
    MsalEntraValidator,
    msal_entra_jwt_validator_config,
)
from aqp_platform_core.auth.rbac import (
    SCOPE_ADMIN_CLUSTER,
    SCOPE_MANAGE_AGENTS,
    SCOPE_MANAGE_INFRA,
    SCOPE_READ_INFRA,
    ALL_SCOPES,
    ALL_CANONICAL_SCOPES,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPERADMIN,
    ROLE_VIEWER,
    expand_role,
    role_grants,
)
from aqp_platform_core.auth.resource_filter import (
    filter_resources,
    has_admin_cluster,
    user_resource_ids,
)

#: The set of identity provider aliases the platform-core shim supports.
SUPPORTED_IDENTITY_PROVIDERS: tuple[str, ...] = (
    "msal_entra",
    "entra",
    "auth0",
    "generic_oidc",
    "mock",
    "cloudflare_access",
)

#: Recognised Entra aliases that all resolve to the MSAL provider.
_ENTRA_ALIASES: frozenset[str] = frozenset({"msal_entra", "entra", "msal", "azure_ad"})


def default_identity_provider_alias() -> str:
    """Return the active platform-wide identity provider alias.

    Entra ID is the primary post-rule-27 + identity.mdc update.
    Reads ``AQP_AUTH_PROVIDER`` first (the existing knob from the
    monolith) and ``AQP_CP_AUTH_PROVIDER`` second so the CP can
    override per-deployment. Defaults to ``"msal_entra"``.

    Recognises a small set of aliases for ergonomic env config:
    ``entra`` / ``msal`` / ``azure_ad`` all map to ``msal_entra``.
    """
    raw = (
        os.environ.get("AQP_AUTH_PROVIDER")
        or os.environ.get("AQP_CP_AUTH_PROVIDER")
        or "msal_entra"
    )
    alias = raw.strip().lower() or "msal_entra"
    if alias in _ENTRA_ALIASES:
        return "msal_entra"
    return alias


def is_entra_primary() -> bool:
    """Return True iff the active provider is the Entra primary path."""
    return default_identity_provider_alias() == "msal_entra"


__all__ = [
    # claims
    "CANONICAL_CLAIMS_NAMESPACE",
    "LEGACY_CLAIMS_NAMESPACE",
    "claim_key",
    "extract_claim",
    # JWT validator
    "JwtValidationError",
    "JwtValidator",
    "JwtValidatorConfig",
    # RBAC scopes
    "SCOPE_ADMIN_CLUSTER",
    "SCOPE_MANAGE_AGENTS",
    "SCOPE_MANAGE_INFRA",
    "SCOPE_READ_INFRA",
    "ALL_SCOPES",
    "ALL_CANONICAL_SCOPES",
    # RBAC roles
    "ROLE_ADMIN",
    "ROLE_OPERATOR",
    "ROLE_SUPERADMIN",
    "ROLE_VIEWER",
    "expand_role",
    "role_grants",
    # Resource filter
    "filter_resources",
    "has_admin_cluster",
    "user_resource_ids",
    # Provider defaults
    "SUPPORTED_IDENTITY_PROVIDERS",
    "default_identity_provider_alias",
    "is_entra_primary",
    # Identity provider shims
    "IdentityProviderShim",
    "IdentityProviderShimConfig",
    "MsalEntraValidator",
    "msal_entra_jwt_validator_config",
    # M2M token broker
    "M2MBrokerError",
    "M2MGrant",
    "M2MTokenBroker",
    "M2MTokenBrokerConfig",
    "broker_for_default_provider",
]
