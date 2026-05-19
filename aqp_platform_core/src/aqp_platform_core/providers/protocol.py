"""InfrastructureProvider ABC — abstract over five backends.

Implementations live in:

- ``aqp_control_plane/src/aqp_cp/providers/docker_compose.py``
- ``aqp_control_plane/src/aqp_cp/providers/kubernetes.py``
- ``aqp_control_plane/src/aqp_cp/providers/aws.py``
- ``aqp_control_plane/src/aqp_cp/providers/azure.py``
- ``aqp_control_plane/src/aqp_cp/providers/gcp.py``

Every concrete implementation:

1. Reads credentials from env vars only (via :class:`SecretStore` chain).
2. Translates :class:`DeploymentSpec` to the backend's native API.
3. Returns a normalised :class:`DeploymentStatus`.
4. Maps backend-specific exceptions to
   :class:`InfrastructureProviderError` subclasses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import DeploymentSpec, DeploymentStatus
from aqp_platform_core.models.health import ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint


class ProviderKind(str, Enum):
    DOCKER_COMPOSE = "docker_compose"
    KUBERNETES = "kubernetes"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class InfrastructureProviderError(RuntimeError):
    """Base class for provider-side failures.

    Subclass to surface provider-specific error codes; the control
    plane API maps these to ``ResponseEnvelope.error``.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.details = details or {}


class InfrastructureProviderUnavailable(InfrastructureProviderError):
    """Raised when the backend is not reachable / not configured.

    The control plane API maps this to ``HTTP 503``.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="provider_unavailable",
            provider=provider,
            details=details,
        )


class InfrastructureProvider(ABC):
    """Pluggable backend for runtime workload operations (AGENTS rule 45).

    Concrete providers MUST override every abstract method. Optional
    methods (``stream_metrics``, ``apply_config``) default to raising
    :class:`InfrastructureProviderUnavailable` so feature-incomplete
    providers fail loud.
    """

    provider_kind: ProviderKind
    provider_alias: str

    # --- Health -------------------------------------------------------

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Return the provider's connectivity / credential health snapshot."""

    # --- Lifecycle ----------------------------------------------------

    @abstractmethod
    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        """Create or update the deployment described by ``spec``.

        Idempotent. If the deployment already exists with the same
        spec hash, returns the current status without making changes.
        """

    @abstractmethod
    async def stop(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:
        """Scale ``service_id`` to zero replicas (or equivalent stopped state)."""

    @abstractmethod
    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Change the replica count of an existing deployment."""

    @abstractmethod
    async def status(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Read the current status of a deployment.

        Returns a status with :attr:`DeploymentLifecyclePhase.UNKNOWN`
        when the deployment does not exist.
        """

    @abstractmethod
    async def list_deployments(
        self,
        *,
        namespace: str | None = None,
    ) -> list[DeploymentStatus]:
        """Return all deployments the active credentials can see.

        The control plane API filters this through
        :func:`aqp_platform_core.auth.resource_filter.filter_resources`
        before returning.
        """

    # --- Config / secrets ---------------------------------------------

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> ServiceConfig:
        """Read the current configuration of ``service_id``.

        Default implementation raises :class:`InfrastructureProviderUnavailable`;
        providers that support config introspection override this.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support get_config",
            provider=self.provider_alias,
        )

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        """Apply a configuration patch.

        Returns ``True`` when the change was applied successfully.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support apply_config",
            provider=self.provider_alias,
        )

    # --- Telemetry ----------------------------------------------------

    async def stream_metrics(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float = 10.0,
    ) -> AsyncIterator[MetricPoint]:
        """Yield :class:`MetricPoint` observations every ``interval_seconds``.

        Default implementation raises :class:`InfrastructureProviderUnavailable`;
        providers that integrate with their backend's metrics service
        override this. Implementations MUST honour the interval — the
        telemetry service uses it for back-pressure.

        Implementations are async generators::

            async def stream_metrics(self, service_id, *, namespace=None, interval_seconds=10.0):
                while True:
                    yield MetricPoint(...)
                    await asyncio.sleep(interval_seconds)
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support stream_metrics",
            provider=self.provider_alias,
        )
        # Unreachable, but satisfies the async-generator signature.
        yield  # type: ignore[unreachable]

    # --- Describe -----------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary for diagnostics endpoints."""
        return {
            "kind": self.provider_kind.value,
            "alias": self.provider_alias,
            "class": self.__class__.__name__,
        }


__all__ = [
    "InfrastructureProvider",
    "InfrastructureProviderError",
    "InfrastructureProviderUnavailable",
    "ProviderKind",
]
