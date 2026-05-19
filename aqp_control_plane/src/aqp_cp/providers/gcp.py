"""GCP :class:`InfrastructureProvider` — GKE (delegates to K8s) + Cloud Run.

Phase 5 ships the registration scaffold + credential probe. Full
:mod:`google.cloud.run_v2` revision-update impl lands in a follow-up PR.
"""
from __future__ import annotations

import logging
import os

from aqp_platform_core.providers.protocol import ProviderKind
from aqp_platform_core.providers.registry import register_provider_class

from aqp_cp.providers._cloud_stub import CloudProviderStub

logger = logging.getLogger(__name__)


@register_provider_class("gcp", replace=True)
class GcpProvider(CloudProviderStub):
    """GCP provider — GKE delegate + Cloud Run scaffold."""

    provider_kind = ProviderKind.GCP
    provider_alias = "gcp"
    cloud_name = "GCP"
    follow_up_pr = "aqp-control-plane#gcp-impl"
    docs_link = "docs/operations/add-new-provider.md#gcp"
    delegate_kubernetes_alias = (
        "kubernetes"
        if os.environ.get("AQP_CP_GCP_DELEGATE_K8S", "").lower() in ("1", "true", "yes")
        else None
    )

    def _real_health_probe(self) -> tuple[bool, dict | None, str | None]:
        """Use google-auth to resolve ADC + project."""
        try:
            import google.auth  # type: ignore[import-not-found]
            from google.auth.exceptions import DefaultCredentialsError  # type: ignore[import-not-found]
        except ImportError:
            return False, None, "google-auth not installed"
        try:
            creds, project = google.auth.default()
            return True, {
                "project": project or os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
                "creds_kind": creds.__class__.__name__,
            }, None
        except DefaultCredentialsError as exc:
            return False, None, f"ADC unavailable: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, None, str(exc)

    def _check_credentials(self) -> tuple[bool, str | None]:
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and os.path.exists(creds_path):
            return True, None
        if os.environ.get("GOOGLE_CLOUD_PROJECT"):
            # ADC: we're probably in a GKE pod with Workload Identity.
            return True, None
        return False, (
            "GCP credentials not found (set GOOGLE_APPLICATION_CREDENTIALS to a "
            "service-account JSON path, or run inside a pod with Workload Identity)."
        )

    def _describe_target(self) -> dict:
        return {
            "project": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            "supports": ["GKE (via kubernetes provider)", "Cloud Run (pending impl)"],
        }


__all__ = ["GcpProvider"]
