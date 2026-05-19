"""InfrastructureProvider ABC + auto-registering metaclass.

Implementations live in:

- ``aqp_control_plane/src/aqp_cp/providers/docker_compose.py``
- ``aqp_control_plane/src/aqp_cp/providers/kubernetes.py``
- ``aqp_control_plane/src/aqp_cp/providers/aws.py``
- ``aqp_control_plane/src/aqp_cp/providers/azure.py``
- ``aqp_control_plane/src/aqp_cp/providers/gcp.py``
- ``aqp_control_plane/src/aqp_cp/providers/cloudflare.py`` (Management Engine)

Every concrete implementation:

1. Reads credentials from env vars only (via :class:`SecretStore` chain).
2. Translates :class:`DeploymentSpec` to the backend's native API.
3. Returns a normalised :class:`DeploymentStatus`.
4. Maps backend-specific exceptions to
   :class:`InfrastructureProviderError` subclasses.

Subclasses are auto-registered via :class:`InfrastructureProviderMeta`
when they set ``provider_alias`` (mirrors
:class:`aqp.kubernetes.protocol.KubernetesAdapterMeta` and
:class:`aqp.auth.providers.protocol.IdentityProviderMeta`). The
function-form :func:`register_provider_class` decorator is retained for
backwards-compat; new providers can ignore it and just set
``provider_alias``.
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any, ClassVar

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import DeploymentSpec, DeploymentStatus
from aqp_platform_core.models.health import ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadExecResult,
    WorkloadLogEvent,
)

logger = logging.getLogger(__name__)


class ProviderKind(str, Enum):
    DOCKER_COMPOSE = "docker_compose"
    KUBERNETES = "kubernetes"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    CLOUDFLARE = "cloudflare"


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


class InfrastructureProviderMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`InfrastructureProvider`.

    Mirrors :class:`aqp.kubernetes.protocol.KubernetesAdapterMeta` and
    :class:`aqp.auth.providers.protocol.IdentityProviderMeta`. Subclasses
    that set ``provider_alias`` (and optionally ``provider_kind``) are
    registered into the process-wide
    :class:`aqp_platform_core.providers.registry.ProviderRegistry`
    automatically — no decorator required.

    Skips registration when the class:

    - Sets ``__abstract_provider__ = True`` on the body
    - Starts with ``Base`` or ``_``
    - Has no ``provider_alias`` (legacy decorator-based registration)
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_provider__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        alias = getattr(cls, "provider_alias", None)
        if not alias:
            return cls
        try:
            from aqp_platform_core.providers.registry import get_provider_registry

            get_provider_registry().register(str(alias), cls, replace=True)
        except Exception:  # noqa: BLE001
            logger.debug(
                "InfrastructureProvider auto-registration failed for %s",
                name,
                exc_info=True,
            )
        return cls


class InfrastructureProvider(metaclass=InfrastructureProviderMeta):
    """Pluggable backend for runtime workload operations (AGENTS rule 45).

    Concrete providers MUST override every abstract method. Optional
    methods (``stream_metrics``, ``apply_config``, ``restart``,
    ``exec``, ``tail_logs``, ``rotate_secret``) default to raising
    :class:`InfrastructureProviderUnavailable` so feature-incomplete
    providers fail loud.

    Subclasses set ``provider_alias`` to enable auto-registration via
    :class:`InfrastructureProviderMeta`.
    """

    __abstract_provider__: ClassVar[bool] = True

    provider_kind: ProviderKind
    provider_alias: str = ""

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

    # --- Management Engine extensions (Phase A) -----------------------
    #
    # These four methods replace the parallel implementations that used
    # to live on :class:`aqp.kubernetes.protocol.KubernetesAdapter`
    # (pod-level ops) and inline in ``aqp_cp.providers.kubernetes`` so
    # the SPA + Theia can call a single client.
    # Defaults raise :class:`InfrastructureProviderUnavailable` so
    # providers can opt out cleanly (e.g. CloudflareProvider has no
    # exec; AWS stub returns unavailable until SDK ships).

    async def restart(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Rolling-restart the deployment without changing its spec.

        Implementations typically annotate the existing manifest with a
        new ``aqp.io/restartedAt`` timestamp (K8s) or trigger
        ``docker compose restart`` (Compose). Returns the post-restart
        :class:`DeploymentStatus`.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support restart",
            provider=self.provider_alias,
        )

    async def exec(
        self,
        service_id: str,
        *,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
        namespace: str | None = None,
    ) -> WorkloadExecResult:
        """Execute ``command`` inside a running container of ``service_id``.

        K8s providers MUST use ``kubernetes.stream.stream`` with
        ``connect_get_namespaced_pod_exec``. Docker SDK providers MUST
        set ``Accept-Encoding: identity`` on the underlying requests
        session (the gigabyte-output latency bug). Returns the full
        :class:`WorkloadExecResult` with stdout / stderr / returncode.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support exec",
            provider=self.provider_alias,
        )

    async def tail_logs(
        self,
        service_id: str,
        *,
        container: str | None = None,
        since_seconds: int | None = None,
        tail: int | None = 200,
        follow: bool = False,
        max_lines: int | None = None,
        namespace: str | None = None,
    ) -> AsyncIterator[WorkloadLogEvent]:
        """Yield :class:`WorkloadLogEvent` frames; never blocks the caller.

        K8s providers MUST pass ``_preload_content=False`` on
        ``read_namespaced_pod_log`` and consume via
        ``kubernetes.watch.Watch().stream(...)`` — the synchronous
        ``follow=True`` path hangs on sparse log emission (the
        documented Kubernetes Python client bug).

        The Management Engine adapts each frame to the canonical
        ``{task_id, stage, message, timestamp, **extras}`` shape per
        AGENTS rule 4 before forwarding to the WebSocket bus.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support tail_logs",
            provider=self.provider_alias,
        )
        # Unreachable, but satisfies the async-generator signature.
        yield  # type: ignore[unreachable]

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        namespace: str | None = None,
    ) -> SecretRotationResult:
        """Rotate ``secret_name`` for ``service_id`` against the provider backend.

        Returns ONLY metadata about the rotation — never the secret
        value. The Management Engine subagent rule
        (``.cursor/rules/aqp-management-engine.mdc``) forbids logging
        secret material; this method's signature enforces that at the
        type level.
        """
        raise InfrastructureProviderUnavailable(
            f"{self.__class__.__name__} does not support rotate_secret",
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
    "InfrastructureProviderMeta",
    "InfrastructureProviderUnavailable",
    "ProviderKind",
]
