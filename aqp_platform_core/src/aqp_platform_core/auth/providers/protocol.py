"""Identity provider shim protocol used by the platform-core boundary.

The shim is intentionally narrow: only what ``aqp_admin`` and
``aqp_control_plane`` need to (a) validate inbound bearers and (b)
mint outbound M2M tokens. First-login provisioning, EntraTenantLink
wizards, SCIM lifecycle, etc. stay in ``aqp/auth/providers/`` so
the monolith retains its single source of truth for the user graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from aqp_platform_core.auth.jwt_validator import (
    JwtValidator,
    JwtValidatorConfig,
)


@dataclass(frozen=True, slots=True)
class IdentityProviderShimConfig:
    """Static configuration for a platform-core identity provider shim.

    Mirrors the upstream :class:`aqp.auth.providers.IdentityProviderConfig`
    fields needed by the boundary surfaces. The shim NEVER reads
    secret material directly — credentials resolve through
    :class:`aqp_platform_core.credentials.CredentialResolver` at the
    M2M broker layer (rule 26).
    """

    provider_alias: str
    issuer: str
    audience: str
    jwks_url: str = ""
    leeway_seconds: int = 60
    jwks_ttl_seconds: int = 600
    algorithms: tuple[str, ...] = ("RS256",)
    expected_claim_namespaces: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class M2MGrant:
    """Result of a client_credentials grant from the active IdP."""

    access_token: str
    expires_at: float
    token_type: str = "Bearer"
    issued_at: float = 0.0
    scope: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class IdentityProviderShim(Protocol):
    """Minimal validator + M2M shim for the platform-core boundary."""

    @property
    def provider_alias(self) -> str:
        """Stable identifier (e.g. ``"msal_entra"``, ``"auth0"``)."""

    @property
    def config(self) -> IdentityProviderShimConfig:
        """Static configuration values for this shim."""

    def jwt_validator(self) -> JwtValidator:
        """Return a cached :class:`JwtValidator` for this shim."""

    def token_endpoint(self) -> str:
        """Return the OIDC token endpoint (used by the M2M broker)."""

    async def acquire_m2m_grant(
        self,
        *,
        client_id: str,
        client_secret: str,
        audience: str,
        scopes: tuple[str, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> M2MGrant:
        """Execute a ``grant_type=client_credentials`` exchange."""


__all__ = [
    "IdentityProviderShim",
    "IdentityProviderShimConfig",
    "JwtValidator",
    "JwtValidatorConfig",
    "M2MGrant",
]
