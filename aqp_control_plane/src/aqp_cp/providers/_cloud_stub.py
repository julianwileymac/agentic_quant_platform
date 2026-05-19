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
    ``_check_credentials()`` / ``_describe_target()`` as needed. The
    workload methods all raise :class:`InfrastructureProviderUnavailable`
    with a structured detail dict so operators can see EXACTLY what's
    missing and which follow-up PR ships the real impl.
    """

    provider_kind: ProviderKind
    provider_alias: str

    # Subclass overrides — name shown in error messages.
    cloud_name: str = "<cloud>"
    follow_up_pr: str = "TBD"
    docs_link: str = "docs/operations/add-new-provider.md"

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

    async def health(self) -> ProviderHealth:
        available, error = self._check_credentials()
        return ProviderHealth(
            provider=self.provider_alias,
            status=HealthStatus.UNAVAILABLE if not available else HealthStatus.DEGRADED,
            available=False,
            last_probe_at=datetime.now(timezone.utc),
            error=error or "stub: workload ops not implemented yet",
            metadata={
                "follow_up_pr": self.follow_up_pr,
                "docs": self.docs_link,
                **self._describe_target(),
            },
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
        raise self._unavailable("status")

    async def list_deployments(
        self, *, namespace: str | None = None
    ) -> list[DeploymentStatus]:
        raise self._unavailable("list_deployments")

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
