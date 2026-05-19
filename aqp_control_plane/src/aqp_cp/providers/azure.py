"""Azure :class:`InfrastructureProvider` — AKS (delegates to K8s) + ACI.

Phase 5 ships the registration scaffold + credential probe. Full
:mod:`azure.mgmt.containerinstance` impl lands in a follow-up PR.
"""
from __future__ import annotations

import logging
import os

from aqp_platform_core.providers.protocol import ProviderKind
from aqp_platform_core.providers.registry import register_provider_class

from aqp_cp.providers._cloud_stub import CloudProviderStub

logger = logging.getLogger(__name__)


@register_provider_class("azure", replace=True)
class AzureProvider(CloudProviderStub):
    """Azure provider — AKS delegate + ACI scaffold."""

    provider_kind = ProviderKind.AZURE
    provider_alias = "azure"
    cloud_name = "Azure"
    follow_up_pr = "aqp-control-plane#azure-impl"
    docs_link = "docs/operations/add-new-provider.md#azure"

    def _check_credentials(self) -> tuple[bool, str | None]:
        # azure-identity supports the same chain as the CLI / Managed
        # Identity / Service Principal. A cheap probe is just "are any
        # of the standard env vars set?".
        sp = (
            os.environ.get("AZURE_CLIENT_ID")
            and os.environ.get("AZURE_TENANT_ID")
            and (
                os.environ.get("AZURE_CLIENT_SECRET")
                or os.environ.get("AZURE_USERNAME")
                or os.environ.get("AZURE_FEDERATED_TOKEN_FILE")
            )
        )
        msi = os.environ.get("MSI_ENDPOINT") or os.environ.get(
            "IDENTITY_ENDPOINT"
        )
        if sp or msi:
            return True, None
        return False, (
            "Azure credentials not found (set AZURE_CLIENT_ID / AZURE_TENANT_ID / "
            "AZURE_CLIENT_SECRET, or run with managed identity)."
        )

    def _describe_target(self) -> dict:
        return {
            "subscription_id": os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
            "supports": ["AKS (via kubernetes provider)", "ACI (pending impl)"],
        }


__all__ = ["AzureProvider"]
