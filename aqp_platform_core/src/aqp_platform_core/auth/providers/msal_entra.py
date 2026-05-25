"""Microsoft Entra ID validator + M2M shim (primary IdP).

The shim is intentionally minimal — only JWT validation + the
client_credentials grant. First-login provisioning and the
EntraTenantLink wizard remain in
``aqp/auth/providers/msal_entra.py`` per AGENTS rule 44.

Issuer / JWKS URL templates follow the Microsoft Entra v2.0 endpoint
conventions:

- ``issuer``    = ``https://login.microsoftonline.com/<tenant>/v2.0``
- ``jwks_url``  = ``https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys``
- ``token_url`` = ``https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token``

``<tenant>`` is one of:

- ``common``         - any Entra tenant + personal Microsoft accounts
- ``organizations``  - any Entra tenant (B2B / external enterprise)
- ``consumers``      - personal Microsoft accounts only
- ``<tenant_id>``    - single-tenant (UUID or verified domain)

For the AQP control plane the recommended default is
``organizations`` (B2B / B2C enterprise customers) with
``audience = "api://aqp-control-plane"`` configured on the Entra
app registration.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from aqp_platform_core.auth.jwt_validator import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
)
from aqp_platform_core.auth.providers.protocol import (
    IdentityProviderShimConfig,
    M2MGrant,
)

_ENTRA_HOST = "https://login.microsoftonline.com"


def msal_entra_jwt_validator_config(
    *,
    tenant: str,
    audience: str,
    leeway_seconds: int = 60,
    jwks_ttl_seconds: int = 600,
    expected_claim_namespaces: tuple[str, ...] = (),
) -> JwtValidatorConfig:
    """Build a :class:`JwtValidatorConfig` for an Entra tenant.

    ``tenant`` may be a UUID, ``common``, ``organizations``, or
    ``consumers``. ``audience`` is the Entra app-registration
    ``api://<app-id-uri>`` resource id.
    """
    tenant_segment = tenant.strip().strip("/") or "organizations"
    issuer = f"{_ENTRA_HOST}/{tenant_segment}/v2.0"
    jwks_url = f"{_ENTRA_HOST}/{tenant_segment}/discovery/v2.0/keys"
    return JwtValidatorConfig(
        issuer=issuer,
        audience=audience,
        algorithms=("RS256",),
        leeway_seconds=leeway_seconds,
        jwks_ttl_seconds=jwks_ttl_seconds,
        jwks_url_override=jwks_url,
        expected_claim_namespaces=expected_claim_namespaces,
    )


@dataclass(frozen=True, slots=True)
class _MsalEntraConfig(IdentityProviderShimConfig):
    """Concrete config carrying the tenant segment used to derive endpoints."""

    tenant_segment: str = "organizations"


class MsalEntraValidator:
    """Microsoft Entra ID validator + M2M shim.

    Owns a single :class:`JwtValidator` and a single
    :class:`httpx.AsyncClient` for the token endpoint. Both are
    lazily created on first use.
    """

    provider_alias = "msal_entra"

    def __init__(
        self,
        *,
        tenant: str,
        audience: str,
        leeway_seconds: int = 60,
        jwks_ttl_seconds: int = 600,
        expected_claim_namespaces: tuple[str, ...] = (),
        http_timeout_seconds: float = 10.0,
    ) -> None:
        tenant_segment = tenant.strip().strip("/") or "organizations"
        self._tenant_segment = tenant_segment
        self._http_timeout = http_timeout_seconds
        self._config = _MsalEntraConfig(
            provider_alias=self.provider_alias,
            issuer=f"{_ENTRA_HOST}/{tenant_segment}/v2.0",
            audience=audience,
            jwks_url=f"{_ENTRA_HOST}/{tenant_segment}/discovery/v2.0/keys",
            leeway_seconds=leeway_seconds,
            jwks_ttl_seconds=jwks_ttl_seconds,
            algorithms=("RS256",),
            expected_claim_namespaces=expected_claim_namespaces,
            tenant_segment=tenant_segment,
        )
        self._validator: JwtValidator | None = None
        self._http: httpx.AsyncClient | None = None

    @property
    def config(self) -> IdentityProviderShimConfig:
        return self._config

    def token_endpoint(self) -> str:
        return f"{_ENTRA_HOST}/{self._tenant_segment}/oauth2/v2.0/token"

    def jwt_validator(self) -> JwtValidator:
        if self._validator is None:
            self._validator = JwtValidator(
                msal_entra_jwt_validator_config(
                    tenant=self._tenant_segment,
                    audience=self._config.audience,
                    leeway_seconds=self._config.leeway_seconds,
                    jwks_ttl_seconds=self._config.jwks_ttl_seconds,
                    expected_claim_namespaces=self._config.expected_claim_namespaces,
                )
            )
        return self._validator

    async def acquire_m2m_grant(
        self,
        *,
        client_id: str,
        client_secret: str,
        audience: str,
        scopes: tuple[str, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> M2MGrant:
        """Execute a ``grant_type=client_credentials`` exchange.

        Entra v2.0 expects the resource as a scope of the form
        ``<audience>/.default``. The optional ``scopes`` argument
        is appended verbatim for callers that want narrower grants.
        """
        await self._ensure_http()
        assert self._http is not None  # narrowed by _ensure_http
        scope_value = self._build_scope(audience, scopes)
        body: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope_value,
        }
        if extra:
            body.update({str(k): str(v) for k, v in extra.items()})
        try:
            response = await self._http.post(
                self.token_endpoint(),
                content=urlencode(body).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise JwtValidationError(
                f"entra token endpoint unreachable: {exc}",
                code="token_endpoint_unreachable",
            ) from exc
        if response.status_code >= 400:
            raise JwtValidationError(
                f"entra client_credentials failed: HTTP {response.status_code}",
                code="m2m_grant_failed",
            )
        data = response.json()
        access_token = str(data.get("access_token") or "")
        if not access_token:
            raise JwtValidationError(
                "entra response missing access_token",
                code="m2m_grant_invalid_response",
            )
        expires_in = int(data.get("expires_in") or 3600)
        granted_scope = data.get("scope")
        scope_tuple = (
            tuple(str(s) for s in str(granted_scope).split() if s)
            if granted_scope
            else scopes
        )
        now = time.time()
        return M2MGrant(
            access_token=access_token,
            expires_at=now + max(60, expires_in - 30),
            token_type=str(data.get("token_type") or "Bearer"),
            issued_at=now,
            scope=scope_tuple,
        )

    async def close(self) -> None:
        if self._validator is not None:
            await self._validator.close()
            self._validator = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _ensure_http(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self._http_timeout,
                headers={"Accept": "application/json"},
            )

    @staticmethod
    def _build_scope(audience: str, scopes: tuple[str, ...]) -> str:
        normalised = audience.rstrip("/")
        if not normalised.endswith("/.default"):
            normalised = f"{normalised}/.default"
        parts = [normalised]
        parts.extend(scopes)
        return " ".join(parts)


__all__ = [
    "MsalEntraValidator",
    "msal_entra_jwt_validator_config",
]
