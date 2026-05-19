"""ConnectivityConfig — env-driven service URL resolution.

The proxy gateway inside ``aqp_client`` reads this at request time so
backend addresses can rotate (e.g. K8s pod IP changes) without
restarting the gateway. The control plane and the SDK in
``rpi_k8s_sdk`` import the same model so all three planes agree on
the URL matrix.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True, slots=True)
class ServiceRoute:
    """Resolved (service, base URL) pair returned by :meth:`ConnectivityConfig.route_for`.

    ``source`` is one of ``"env"`` (read from a dedicated env var),
    ``"ingress"`` (derived from ``AQP_INGRESS_BASE_URL``), or
    ``"default"`` (compose-default fallback). The proxy gateway logs
    this so operators can debug "why did my request go there?" quickly.
    """

    service: str
    base_url: str
    source: str


class ConnectivityConfig(BaseSettings):
    """Service URL matrix used by the ``aqp_client`` reverse proxy and the SDK.

    Every field has both a compose-friendly default and a K8s-friendly
    override pattern documented per field. The :meth:`route_for` method
    centralises the env-vs-ingress decision logic.
    """

    model_config = SettingsConfigDict(
        env_prefix="AQP_",
        case_sensitive=False,
        extra="ignore",
        env_file=None,
        # NOTE: we intentionally DO NOT auto-load a .env file here;
        # connectivity is a runtime concern and the FastAPI process
        # may have many env vars beyond the URL matrix. Keep this
        # narrow to avoid surprising the operator.
    )

    # --- Core service URLs ------------------------------------------------
    core_api_url: str = Field(
        default="http://aqp-core:8000",
        description="Base URL for the AQP core FastAPI API (business routes).",
        alias="AQP_CORE_API_URL",
    )
    ml_api_url: str = Field(
        default="http://aqp-ml:8001",
        description="Base URL for the AQP ML / testing framework API.",
        alias="AQP_ML_API_URL",
    )
    mcp_url: str = Field(
        default="http://aqp-mcp:8002",
        description="Base URL for the DataMCP HTTP router.",
        alias="AQP_MCP_URL",
    )
    redis_url: str = Field(
        default="redis://redis-stack:6379",
        description="Redis URL (HierarchicalRAG store + cache + progress bus).",
        alias="AQP_REDIS_URL",
    )
    control_plane_url: str = Field(
        default="http://aqp-cp:9000",
        description="Base URL for the aqp_control_plane micro-project.",
        alias="AQP_CONTROL_PLANE_URL",
    )

    # --- Hybrid / external ingress mode ----------------------------------
    ingress_base_url: str = Field(
        default="",
        description=(
            "When non-empty, all service URLs are derived by appending "
            "standard path prefixes to this base. Overrides the per-service "
            "URLs above. Use for production Kubernetes deployments behind a "
            "single Ingress."
        ),
        alias="AQP_INGRESS_BASE_URL",
    )

    # --- Path prefixes (used when ingress_base_url is set) ---------------
    core_path_prefix: str = Field(
        default="/api",
        description="Path prefix for the core API when behind an Ingress.",
    )
    ml_path_prefix: str = Field(
        default="/ml",
        description="Path prefix for the ML API when behind an Ingress.",
    )
    mcp_path_prefix: str = Field(
        default="/mcp",
        description="Path prefix for the MCP router when behind an Ingress.",
    )
    control_plane_path_prefix: str = Field(
        default="/manage",
        description="Path prefix for the control plane when behind an Ingress.",
    )

    # --- Healthcheck + retry --------------------------------------------
    healthcheck_path: str = Field(
        default="/health",
        description="Path on every service the proxy uses for readiness probes.",
    )
    upstream_connect_timeout_seconds: float = Field(
        default=3.0,
        ge=0.1,
        le=30.0,
        description="httpx connect timeout for upstream proxy calls.",
    )
    upstream_read_timeout_seconds: float = Field(
        default=30.0,
        ge=0.1,
        le=300.0,
        description="httpx read timeout for upstream proxy calls.",
    )
    websocket_max_reconnect_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description=(
            "Maximum reconnect attempts when an upstream WebSocket "
            "disconnects (e.g. pod rotation). 0 disables reconnect."
        ),
    )
    websocket_reconnect_backoff_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=30.0,
        description="Initial backoff for WebSocket reconnect (exponential).",
    )

    # --- M2M for proxy-injected Authorization ---------------------------
    m2m_token_audience: str = Field(
        default="",
        description=(
            "When set, the gateway proxy fetches an M2M token for this "
            "audience and injects it as 'Authorization: Bearer <token>' "
            "on proxied requests to the control plane. Empty disables "
            "M2M injection (dev mode)."
        ),
        alias="AQP_CONTROL_PLANE_M2M_AUDIENCE",
    )

    SERVICE_PREFIX_FIELDS: ClassVar[dict[str, str]] = {
        "core": "core_path_prefix",
        "ml": "ml_path_prefix",
        "mcp": "mcp_path_prefix",
        "control_plane": "control_plane_path_prefix",
    }

    SERVICE_URL_FIELDS: ClassVar[dict[str, str]] = {
        "core": "core_api_url",
        "ml": "ml_api_url",
        "mcp": "mcp_url",
        "control_plane": "control_plane_url",
    }

    @field_validator(
        "core_api_url",
        "ml_api_url",
        "mcp_url",
        "control_plane_url",
        "ingress_base_url",
    )
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        """Drop trailing slash so route_for() builds consistent URLs."""
        if not v:
            return v
        return v.rstrip("/")

    def route_for(self, service: str) -> ServiceRoute:
        """Resolve a logical service name to its base URL.

        Precedence:

        1. ``AQP_INGRESS_BASE_URL`` + the matching path prefix (highest)
        2. The per-service env var (``AQP_CORE_API_URL``, etc.)
        3. The compose-friendly default

        Raises ``ValueError`` for unknown services so a typo in the
        gateway proxy fails loud.
        """
        if service not in self.SERVICE_URL_FIELDS:
            known = ", ".join(sorted(self.SERVICE_URL_FIELDS))
            raise ValueError(
                f"Unknown service {service!r} (expected one of: {known})"
            )

        if self.ingress_base_url:
            prefix = getattr(self, self.SERVICE_PREFIX_FIELDS[service])
            return ServiceRoute(
                service=service,
                base_url=f"{self.ingress_base_url}{prefix}",
                source="ingress",
            )

        url = getattr(self, self.SERVICE_URL_FIELDS[service])
        # Distinguish env-overridden from default by re-loading defaults;
        # cheap and avoids needing to track source through pydantic.
        defaults = self.__class__.model_fields[self.SERVICE_URL_FIELDS[service]].default
        source = "env" if url != defaults else "default"
        return ServiceRoute(service=service, base_url=url, source=source)


_INSTANCE: ConnectivityConfig | None = None
_LOCK = threading.Lock()


def get_connectivity_config() -> ConnectivityConfig:
    """Process-wide singleton getter — reads env once per process.

    Use :func:`reset_connectivity_config` in tests to force a re-read.
    """
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = ConnectivityConfig()  # type: ignore[call-arg]
    return _INSTANCE


def reset_connectivity_config() -> None:
    """Drop the cached singleton so the next call re-reads env vars."""
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None


__all__ = [
    "ConnectivityConfig",
    "ServiceRoute",
    "get_connectivity_config",
    "reset_connectivity_config",
]
