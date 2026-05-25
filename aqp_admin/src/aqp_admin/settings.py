"""Settings for the aqp_admin backend.

Reads ``AQP_ADMIN_*`` environment variables and falls back to safe local
defaults. Per AQP rule 7 the project never instantiates a fresh settings
object directly; consumers go through :func:`get_settings`.

Auth defaults align with the Entra-primary identity decision: the
admin BFF validates inbound bearers against the Microsoft Entra v2.0
issuer and mints outbound M2M tokens (admin -> control plane) through
the platform-core M2M broker. Auth0 stays available as a fallback by
setting ``AQP_ADMIN_AUTH_PROVIDER=auth0``.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",  # mix AQP_ADMIN_*, AQP_AUTH_*, AQP_CP_* without per-class prefix
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service topology ----------------------------------------------
    api_url: str = Field(
        default="http://localhost:8000",
        alias="AQP_ADMIN_API_URL",
        description="AQP monolith base URL.",
    )
    control_plane_url: str = Field(
        default="http://localhost:9000",
        alias="AQP_ADMIN_CONTROL_PLANE_URL",
        description="aqp_control_plane base URL.",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3003"],
        alias="AQP_ADMIN_CORS_ORIGINS",
        description="Allowed CORS origins for the admin SPA.",
    )

    # --- Auth (Entra-primary, Auth0 fallback) --------------------------
    auth_required: bool = Field(
        default=True,
        alias="AQP_ADMIN_AUTH_REQUIRED",
        description="Set False only for local sandboxes; never in production.",
    )
    auth_provider: str = Field(
        default="msal_entra",
        alias="AQP_ADMIN_AUTH_PROVIDER",
        description=(
            "Active identity provider alias. Entra ID is the primary "
            "post the rule-27 + identity.mdc update; flip to 'auth0' "
            "for legacy / B2C deployments."
        ),
    )
    auth_entra_tenant: str = Field(
        default="organizations",
        alias="AQP_ADMIN_ENTRA_TENANT",
        description=(
            "Entra tenant segment used to derive issuer + JWKS URLs. "
            "Use a tenant UUID for single-tenant, 'organizations' for "
            "any Entra tenant (B2B), 'common' to additionally accept "
            "personal Microsoft accounts."
        ),
    )
    auth_oidc_issuer: str = Field(
        default="",
        alias="AQP_AUTH_OIDC_ISSUER",
        description=(
            "Explicit OIDC issuer URL. When empty the Entra default is "
            "derived from auth_entra_tenant."
        ),
    )
    auth_oidc_audience: str = Field(
        default="api://aqp-admin",
        alias="AQP_AUTH_OIDC_AUDIENCE",
        description="API resource identifier configured on the IdP.",
    )
    auth_claims_namespace: str = Field(
        default="https://aqp.internal/",
        alias="AQP_AUTH_CLAIMS_NAMESPACE",
    )
    auth_claims_namespace_aliases: list[str] = Field(
        default_factory=lambda: ["https://aqp/"],
        alias="AQP_AUTH_CLAIMS_NAMESPACE_ALIASES",
    )
    auth_jwks_ttl_seconds: int = Field(
        default=600,
        alias="AQP_ADMIN_AUTH_JWKS_TTL_SECONDS",
        ge=60,
    )
    auth_leeway_seconds: int = Field(
        default=60,
        alias="AQP_ADMIN_AUTH_LEEWAY_SECONDS",
        ge=0,
        le=300,
    )

    # --- M2M broker (admin -> control plane) ---------------------------
    m2m_credential_service: str = Field(
        default="aqp-admin-to-cp",
        alias="AQP_ADMIN_M2M_CREDENTIAL_SERVICE",
        description=(
            "CredentialResolver service name for the admin BFF's "
            "control-plane client credentials."
        ),
    )
    m2m_credential_purpose: str = Field(
        default="client_credentials",
        alias="AQP_ADMIN_M2M_CREDENTIAL_PURPOSE",
    )
    m2m_cp_audience: str = Field(
        default="api://aqp-control-plane",
        alias="AQP_ADMIN_M2M_CP_AUDIENCE",
        description="Audience claim the control plane validates on incoming M2M tokens.",
    )

    # --- Audit ---------------------------------------------------------
    audit_sink: str = Field(
        default="jsonl",
        alias="AQP_ADMIN_AUDIT_SINK",
        description="Audit sink: 'jsonl' for local file or 'http' to post to monolith.",
    )
    audit_jsonl_path: str = Field(
        default="./admin_audit.jsonl",
        alias="AQP_ADMIN_AUDIT_JSONL_PATH",
        description="JSONL fallback path when audit_sink == 'jsonl'.",
    )
    audit_http_url: str = Field(
        default="",
        alias="AQP_ADMIN_AUDIT_HTTP_URL",
        description=(
            "Monolith audit ingest URL (e.g. "
            "http://localhost:8000/_internal/audit/admin-runs). "
            "Required when audit_sink == 'http'."
        ),
    )

    @property
    def auth_enabled(self) -> bool:
        """Auth requires both ``auth_required=true`` and a resolvable issuer."""
        if not self.auth_required:
            return False
        if self.auth_oidc_issuer:
            return True
        # Entra-primary path derives the issuer from the tenant segment.
        return bool(self.auth_entra_tenant)


@lru_cache(maxsize=1)
def get_settings() -> AdminSettings:
    return AdminSettings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
