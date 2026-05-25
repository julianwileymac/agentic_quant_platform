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
            "aqp_platform/configs/deployment/topology.yaml. When set, this overrides "
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
        default="aqp_platform/deployments/compose/docker-compose.local.yml",
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
    audit_sink: str = Field(
        default="jsonl",
        alias="AQP_CP_AUDIT_SINK",
        description=(
            "Audit sink for WorkloadRun + TerraformRun rows. "
            "'jsonl' writes locally (default); 'http' posts to the monolith "
            "audit ingest URL (see audit_http_url); 'logging' is a no-op "
            "fallback that only emits structured log lines."
        ),
    )
    audit_http_url: str = Field(
        default="",
        alias="AQP_CP_AUDIT_HTTP_URL",
        description=(
            "Monolith audit ingest URL (e.g. "
            "http://localhost:8000/_internal/audit/workload-runs). Required "
            "when audit_sink == 'http'. The HTTP sink uses the M2M broker "
            "to attach a Bearer token (Entra-primary, Auth0 fallback)."
        ),
    )

    # --- Tenant namespace bootstrap (Phase 1) ---------------------------
    tenant_namespace_prefix: str = Field(
        default="tenant",
        alias="AQP_CP_TENANT_NAMESPACE_PREFIX",
        description="Prefix for tenant namespaces (Namespace becomes '{prefix}-{tenant_id}').",
    )

    # --- Kaniko in-cluster image builder (Phase 1) ----------------------
    kaniko_image: str = Field(
        default="ghcr.io/chainguard-dev/kaniko:latest",
        alias="AQP_CP_KANIKO_IMAGE",
        description=(
            "Kaniko OCI image used for in-cluster builds. The original "
            "GoogleContainerTools/kaniko repo was archived June 2025; the "
            "Chainguard fork is the maintained continuation. Pin by SHA "
            "in production."
        ),
    )
    kaniko_builder_sa: str = Field(
        default="kaniko-builder",
        alias="AQP_CP_KANIKO_BUILDER_SA",
        description=(
            "ServiceAccount that the Kaniko Job pod assumes. Cloud "
            "credentials resolve through EKS Pod Identity / IRSA / "
            "Workload Identity Federation — NEVER through Kubernetes Secrets."
        ),
    )
    kaniko_namespace_default: str = Field(
        default="aqp-builds",
        alias="AQP_CP_KANIKO_NAMESPACE_DEFAULT",
        description="Namespace where Kaniko Jobs run by default.",
    )
    kaniko_ttl_seconds_after_finished: int = Field(
        default=600,
        alias="AQP_CP_KANIKO_TTL_SECONDS_AFTER_FINISHED",
        ge=60,
        le=86400,
    )
    kaniko_backoff_limit: int = Field(
        default=2,
        alias="AQP_CP_KANIKO_BACKOFF_LIMIT",
        ge=0,
        le=10,
    )

    # --- Terraform IaC runtime (Phase 0 / rule-42 relocation) -----------
    terraform_workspaces_dir: str = Field(
        default="./terraform_workspaces",
        alias="AQP_CP_TERRAFORM_WORKSPACES_DIR",
        description=(
            "Filesystem root for per-workspace state + rendered HCL. "
            "Must be writable by the runner pod."
        ),
    )
    terraform_executor_image: str = Field(
        default="hashicorp/terraform:1.10",
        alias="AQP_CP_TERRAFORM_EXECUTOR_IMAGE",
        description="OCI image used by the Terraform executor pod.",
    )
    terraform_state_backend: str = Field(
        default="local",
        alias="AQP_CP_TERRAFORM_STATE_BACKEND",
        description="Default state backend: local / s3 / azurerm / gcs / hcp.",
    )
    terraform_hcp_org: str = Field(
        default="",
        alias="AQP_CP_TERRAFORM_HCP_ORG",
        description=(
            "HCP Terraform organization name. Empty disables the HCP path; "
            "credentials still resolve through CredentialResolver."
        ),
    )
    terraform_kill_switch_secret_path: str = Field(
        default="/tmp/aqp-terraform-killswitch",  # noqa: S108
        alias="AQP_CP_TERRAFORM_KILL_SWITCH_SECRET_PATH",
        description=(
            "Filesystem path (tmpfs) where the kill-switch sentinel "
            "lives. Existence of the file blocks new apply / destroy."
        ),
    )

    # --- Observability (Phase 1 — identity-aware Prometheus proxy) ------
    prometheus_url: str = Field(
        default="http://prometheus.monitoring.svc.cluster.local:9090",
        alias="AQP_CP_PROMETHEUS_URL",
        description="Prometheus base URL the identity-aware proxy talks to.",
    )
    prometheus_tenant_label: str = Field(
        default="aqp_tenant",
        alias="AQP_CP_PROMETHEUS_TENANT_LABEL",
        description=(
            "Label name injected into every PromQL selector so users only "
            "see metrics from their own tenant namespace."
        ),
    )
    prometheus_deny_metrics: list[str] = Field(
        default_factory=lambda: [
            "up",
            "process_*",
            "go_*",
            "node_*",
            "kube_node_*",
            "prometheus_*",
        ],
        alias="AQP_CP_PROMETHEUS_DENY_METRICS",
        description=(
            "Metric-name patterns that are NEVER returned cross-tenant. "
            "Used as a deny list during PromQL rewriting."
        ),
    )

    # --- M2M broker (Phase 0 — admin -> CP, CP -> monolith) -------------
    auth_provider: str = Field(
        default="msal_entra",
        alias="AQP_CP_AUTH_PROVIDER",
        description=(
            "Active identity provider alias. Entra ID is the primary "
            "post the rule-27 + identity.mdc update; flip to 'auth0' "
            "for legacy / B2C deployments."
        ),
    )
    auth_entra_tenant: str = Field(
        default="organizations",
        alias="AQP_CP_ENTRA_TENANT",
        description=(
            "Entra tenant segment used to derive issuer + JWKS URLs."
        ),
    )
    m2m_credential_service: str = Field(
        default="aqp-cp-to-monolith",
        alias="AQP_CP_M2M_CREDENTIAL_SERVICE",
        description=(
            "CredentialResolver service name for CP -> monolith client credentials."
        ),
    )
    m2m_credential_purpose: str = Field(
        default="client_credentials",
        alias="AQP_CP_M2M_CREDENTIAL_PURPOSE",
    )
    m2m_monolith_audience: str = Field(
        default="api://aqp-monolith",
        alias="AQP_CP_M2M_MONOLITH_AUDIENCE",
        description="Audience claim the monolith validates on incoming M2M tokens.",
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
            "aqp_platform/deployments/kubernetes/rollback/legacy-management/ during a rollback."
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
