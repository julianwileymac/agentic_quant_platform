"""Shared scaffold for cloud-provider implementations (AWS / Azure / GCP).

The full SDK-backed implementations for the three public clouds are
non-trivial and need real cloud accounts to test against. Phase 5
ships:

- Full ``docker_compose`` provider (local dev path)
- Full ``kubernetes`` provider (production target)
- Cloud-provider STUBS that register against the InfrastructureProvider
  ABC, surface correctly in :func:`list_providers`, and return
  structured ``InfrastructureProviderUnavailable`` errors for every
  workload op. The error message points operators at the follow-up
  PR / runbook.

Each cloud stub:

- Validates that its credential chain is satisfiable BEFORE accepting
  any workload op (returns ``ProviderHealth.status=UNAVAILABLE``
  otherwise).
- Optionally delegates to the :class:`KubernetesProvider` when the
  active workload runs on a managed K8s service (EKS / AKS / GKE) and
  the operator pre-attached the kubeconfig.

The full SDK impl will land in three follow-up PRs (one per cloud).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import DeploymentSpec, DeploymentStatus
from aqp_platform_core.models.health import HealthStatus, ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderUnavailable,
    ProviderKind,
)

logger = logging.getLogger(__name__)


class CloudProviderStub(InfrastructureProvider):
    """Base class for the three cloud-provider stubs.

    Subclasses set ``provider_kind`` + ``provider_alias`` and override
    ``_check_credentials()`` / ``_describe_target()`` as needed. Write
    ops still raise :class:`InfrastructureProviderUnavailable` with a
    structured detail dict so operators can see EXACTLY what's missing
    and which follow-up PR ships the real impl.

    Read ops (``health`` + ``list_deployments`` + ``status``) get a
    best-effort real implementation when subclasses implement
    :meth:`_real_health_probe` (returns ``(ok, metadata)``) and / or
    set ``delegate_kubernetes_alias`` — in which case
    :meth:`list_deployments` and :meth:`status` delegate to the
    registered K8s provider so EKS / AKS / GKE workloads show up in
    the Management Studio without waiting for full per-cloud SDKs.
    """

    provider_kind: ProviderKind
    provider_alias: str

    # Subclass overrides — name shown in error messages.
    cloud_name: str = "<cloud>"
    follow_up_pr: str = "TBD"
    docs_link: str = "docs/operations/add-new-provider.md"

    # When set + the alias is registered, list_deployments + status delegate.
    delegate_kubernetes_alias: str | None = None

    def _unavailable(self, action: str) -> InfrastructureProviderUnavailable:
        return InfrastructureProviderUnavailable(
            (
                f"{self.cloud_name} {action} not yet implemented in this "
                f"build. Tracking in follow-up PR {self.follow_up_pr}; see "
                f"{self.docs_link} for the implementation plan."
            ),
            provider=self.provider_alias,
            details={
                "action": action,
                "cloud": self.cloud_name,
                "follow_up_pr": self.follow_up_pr,
                "docs": self.docs_link,
            },
        )

    def _check_credentials(self) -> tuple[bool, str | None]:
        """Best-effort credential probe; override per cloud.

        Returns ``(available, error_or_none)``. The default
        implementation reports unavailable + a generic message.
        """
        return False, f"{self.cloud_name} credential chain not configured"

    def _describe_target(self) -> dict[str, Any]:
        """Provider metadata returned by :meth:`health` and :meth:`describe`."""
        return {}

    def _real_health_probe(self) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Optional best-effort real health probe.

        Subclasses override to make a single cheap SDK call (STS
        ``get_caller_identity``, ``ResourceManagerClient.subscriptions.list``,
        ``cloudresourcemanager.projects.get``, ...) and return
        ``(ok, metadata, error)``. The default returns
        ``(False, None, None)`` which means "no real probe was
        attempted; fall back to the credential-only check".
        """
        return False, None, None

    async def health(self) -> ProviderHealth:
        available, error = self._check_credentials()
        if not available:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=datetime.now(timezone.utc),
                error=error or "credentials not configured",
                metadata={
                    "follow_up_pr": self.follow_up_pr,
                    "docs": self.docs_link,
                    **self._describe_target(),
                },
            )
        # Credentials look OK — try the real SDK probe (best-effort).
        try:
            ok, meta, probe_error = await asyncio.to_thread(self._real_health_probe)
        except Exception as exc:  # noqa: BLE001
            ok, meta, probe_error = False, None, str(exc)
        status_value = (
            HealthStatus.OK if ok else HealthStatus.DEGRADED
        )
        merged_meta: dict[str, Any] = {
            "follow_up_pr": self.follow_up_pr,
            "docs": self.docs_link,
            **self._describe_target(),
        }
        if meta:
            merged_meta.update(meta)
        return ProviderHealth(
            provider=self.provider_alias,
            status=status_value,
            available=bool(ok),
            last_probe_at=datetime.now(timezone.utc),
            error=probe_error if not ok else None,
            metadata=merged_meta,
        )

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        raise self._unavailable("start")

    async def stop(
        self, service_id: str, *, namespace: str | None = None
    ) -> DeploymentStatus:
        raise self._unavailable("stop")

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        raise self._unavailable("scale")

    async def status(
        self, service_id: str, *, namespace: str | None = None
    ) -> DeploymentStatus:
        k8s = self._maybe_kubernetes_provider()
        if k8s is not None:
            return await k8s.status(service_id, namespace=namespace)
        raise self._unavailable("status")

    async def list_deployments(
        self, *, namespace: str | None = None
    ) -> list[DeploymentStatus]:
        k8s = self._maybe_kubernetes_provider()
        if k8s is not None:
            return await k8s.list_deployments(namespace=namespace)
        raise self._unavailable("list_deployments")

    def _maybe_kubernetes_provider(self) -> InfrastructureProvider | None:
        """Return the registered K8s provider when delegation is configured.

        Subclasses set :attr:`delegate_kubernetes_alias` to enable; the
        Management Studio surface gets read-only EKS / AKS / GKE
        coverage today without waiting for per-cloud SDK impls.
        """
        if not self.delegate_kubernetes_alias:
            return None
        try:
            from aqp_platform_core.providers.registry import get_provider_registry

            return get_provider_registry().get_or_create(
                self.delegate_kubernetes_alias
            )
        except Exception:  # noqa: BLE001
            return None

    async def get_config(
        self, service_id: str, *, namespace: str | None = None
    ) -> ServiceConfig:
        raise self._unavailable("get_config")

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        raise self._unavailable("apply_config")

    async def stream_metrics(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float = 10.0,
    ) -> AsyncIterator[MetricPoint]:
        raise self._unavailable("stream_metrics")
        # Unreachable but satisfies the async-generator signature.
        yield  # type: ignore[unreachable]


__all__ = ["CloudProviderStub"]
