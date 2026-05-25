"""Identity provider shims for the platform-core boundary.

These shims expose JWT validation + M2M client-credentials surfaces
ONLY. First-login provisioning + user lifecycle remain in
``aqp/auth/providers/`` (the monolith owns the Postgres-backed user
graph and the EntraTenantLink wizard).

The shims exist so ``aqp_admin`` and ``aqp_control_plane`` can:

1. Validate inbound bearer JWTs against the active identity provider's
   JWKS without importing from ``aqp.*``.
2. Mint outbound M2M tokens via the
   :class:`aqp_platform_core.auth.m2m.M2MTokenBroker` for admin -> CP
   and CP -> monolith calls.

Two providers ship today:

- :class:`MsalEntraValidator` — Microsoft Entra ID (primary IdP after
  the rule-44 + identity.mdc update).
- :class:`Auth0Validator` — fallback for the B2C self-signup pool.

Both implement the :class:`IdentityProviderShim` protocol so the M2M
broker can target whichever is active without branching.
"""
from __future__ import annotations

from aqp_platform_core.auth.providers.msal_entra import (
    MsalEntraValidator,
    msal_entra_jwt_validator_config,
)
from aqp_platform_core.auth.providers.protocol import (
    IdentityProviderShim,
    IdentityProviderShimConfig,
    M2MGrant,
)

__all__ = [
    "IdentityProviderShim",
    "IdentityProviderShimConfig",
    "M2MGrant",
    "MsalEntraValidator",
    "msal_entra_jwt_validator_config",
]
