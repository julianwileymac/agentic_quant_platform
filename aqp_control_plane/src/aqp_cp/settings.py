"""Control-plane settings (pydantic-settings, AQP_* env prefix)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ControlPlaneSettings(BaseSettings):
    """Single source of truth for control-plane configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",  # we mix AQP_*, AUTH0_*, AWS_*, AZURE_*, GOOGLE_* keys
        case_sensitive=False,
        extra="ignore",
    )

    # --- Provider selection ----------------------------------------------
    provider: str = Field(
        default="docker_compose",
        alias="AQP_CP_PROVIDER",
        description=(
            "Active InfrastructureProvider alias — one of: "
            "'docker_compose', 'kubernetes', 'aws', 'azure', 'gcp'."
        ),
    )
    topology_target_id: str = Field(
        default="",
        alias="AQP_CP_TOPOLOGY_TARGET_ID",
        description=(
            "Optional explicit deployment target id from "
            "configs/deployment/topology.yaml. When set, this overrides "
            "provider-based target inference."
        ),
    )

    # --- Auth ------------------------------------------------------------
    auth_required: bool = Field(
        default=True,
        alias="AQP_CP_AUTH_REQUIRED",
        description="Set False only for local sandboxes — never in production.",
    )
    auth_oidc_issuer: str = Field(
        default="",
        alias="AQP_AUTH_OIDC_ISSUER",
        description="Auth0 tenant URL with trailing slash.",
    )
    auth_oidc_audience: str = Field(
        default="https://api.aqp.internal/manage",
        alias="AQP_AUTH_OIDC_AUDIENCE",
        description="API resource identifier configured in Auth0.",
    )
    auth_claims_namespace: str = Field(
        default="https://aqp.internal/",
        alias="AQP_AUTH_CLAIMS_NAMESPACE",
    )
    auth_claims_namespace_aliases: list[str] = Field(
        default_factory=lambda: ["https://aqp/"],
        alias="AQP_AUTH_CLAIMS_NAMESPACE_ALIASES",
        description=(
            "Legacy claim namespaces still readable by the validator for the "
            "one-release migration window (ADR 003)."
        ),
    )
    auth_jwks_ttl_seconds: int = Field(
        default=600,
        alias="AQP_CP_AUTH_JWKS_TTL_SECONDS",
        ge=60,
    )
    auth_leeway_seconds: int = Field(
        default=60,
        alias="AQP_CP_AUTH_LEEWAY_SECONDS",
        ge=0,
        le=300,
    )

    # --- docker_compose provider ----------------------------------------
    compose_file: str = Field(
        default="deployments/compose/docker-compose.local.yml",
        alias="AQP_CP_COMPOSE_FILE",
    )
    compose_project_name: str = Field(
        default="aqp",
        alias="AQP_CP_COMPOSE_PROJECT_NAME",
    )

    # --- kubernetes provider --------------------------------------------
    kubeconfig_path: str = Field(
        default="",
        alias="AQP_CP_KUBECONFIG_PATH",
        description="Empty -> in-cluster config; otherwise path to kubeconfig.",
    )
    kube_context: str = Field(
        default="",
        alias="AQP_CP_KUBE_CONTEXT",
    )
    kube_namespace_default: str = Field(
        default="aqp",
        alias="AQP_CP_KUBE_NAMESPACE_DEFAULT",
    )

    # --- Telemetry -------------------------------------------------------
    telemetry_interval_seconds: float = Field(
        default=10.0,
        alias="AQP_CP_TELEMETRY_INTERVAL_SECONDS",
        ge=1.0,
        le=300.0,
    )
    alert_cpu_critical_pct: float = Field(
        default=85.0,
        alias="AQP_CP_ALERT_CPU_CRITICAL_PCT",
        ge=0.0,
        le=100.0,
    )
    alert_memory_critical_pct: float = Field(
        default=90.0,
        alias="AQP_CP_ALERT_MEMORY_CRITICAL_PCT",
        ge=0.0,
        le=100.0,
    )

    # --- Audit ledger ----------------------------------------------------
    audit_log_path: str = Field(
        default="",
        alias="AQP_CP_AUDIT_LOG_PATH",
        description=(
            "Optional path for a JSONL audit log written on top of structured "
            "logging. Empty disables file-based audit (relies on stdout)."
        ),
    )

    # --- Legacy rpi-k8s-management fallback ------------------------------
    legacy_fallback: bool = Field(
        default=False,
        alias="AQP_CONTROL_PLANE_LEGACY_FALLBACK",
        description=(
            "Emergency rollback flag for the deprecated rpi-k8s-management "
            "API. Default False - AQP is decoupled from rpi_kubernetes; "
            "the canonical surface is /manage/streaming/*, "
            "/manage/observability/*, /manage/lakehouse/*, "
            "/manage/timeseries/*, and /manage/data-plane/*. Only set True "
            "to re-enable the passthrough to the v1-final image pinned in "
            "rpi_kubernetes/kubernetes/legacy-management/ during a rollback."
        ),
    )

    @property
    def auth_enabled(self) -> bool:
        """Auth requires both ``auth_required=true`` and a configured issuer."""
        return bool(self.auth_required) and bool(self.auth_oidc_issuer)


@lru_cache(maxsize=1)
def get_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()


__all__ = ["ControlPlaneSettings", "get_settings", "reset_settings_cache"]
