"""Azure AKS :class:`KubernetesAdapter` — auth via azure-identity + AKS Mgmt API.

Subclasses :class:`InClusterAdapter`; only :meth:`_load_config`
differs. Uses :class:`azure.identity.DefaultAzureCredential` so the
adapter automatically picks up:

- Operator laptop: ``az login`` cached credentials
- CI: ``AZURE_CLIENT_ID`` / ``AZURE_CLIENT_SECRET`` / ``AZURE_TENANT_ID``
- In-cluster: Azure Workload Identity (preferred) or pod-identity

Calls :class:`ContainerServiceClient.managed_clusters.list_cluster_user_credentials`
to fetch a kubeconfig blob, which we parse and stuff into a
:class:`kubernetes.client.Configuration`.

Azure SDKs are optional: missing imports degrade
:meth:`is_available` to ``False`` so routes return 503.
"""
from __future__ import annotations

import base64
import logging
import tempfile
from typing import Any

from aqp.kubernetes.adapters.in_cluster import InClusterAdapter

logger = logging.getLogger(__name__)


class AzureAksAdapter(InClusterAdapter):
    """Azure AKS adapter built on the standard kubernetes-python-client."""

    adapter_kind = "azure_aks"
    adapter_alias = "AzureAksAdapter"

    def __init__(self) -> None:
        self._loaded = False
        self._k8s_module = None
        self._cluster_name: str | None = None
        self._resource_group: str | None = None
        self._subscription_id: str | None = None
        try:
            self._load_config()
        except Exception as exc:  # noqa: BLE001
            logger.debug("AzureAksAdapter unavailable: %s", exc)

    def _load_config(self) -> None:  # type: ignore[override]
        try:
            import kubernetes as k8s  # type: ignore
            import yaml  # type: ignore
        except ImportError:
            self._loaded = False
            return
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore
            from azure.mgmt.containerservice import (  # type: ignore
                ContainerServiceClient,
            )
        except ImportError:
            logger.info(
                "AzureAksAdapter requires azure-identity + "
                "azure-mgmt-containerservice; install with "
                "'pip install agentic-quant-platform[cloud-azure]'"
            )
            self._loaded = False
            return

        try:
            from aqp.config import settings

            cluster_name = (str(getattr(settings, "azure_aks_cluster_name", "") or "")).strip()
            resource_group = (str(getattr(settings, "azure_resource_group", "") or "")).strip()
            subscription_id = (str(getattr(settings, "azure_subscription_id", "") or "")).strip()
        except Exception:
            cluster_name = resource_group = subscription_id = ""

        if not cluster_name or not resource_group or not subscription_id:
            logger.info(
                "AzureAksAdapter: AQP_AZURE_AKS_CLUSTER_NAME / AQP_AZURE_RESOURCE_GROUP "
                "/ AQP_AZURE_SUBSCRIPTION_ID not all set; disabled"
            )
            self._loaded = False
            return

        try:
            credential = DefaultAzureCredential()
            client = ContainerServiceClient(credential, subscription_id)
            kubeconfigs = client.managed_clusters.list_cluster_user_credentials(
                resource_group_name=resource_group,
                resource_name=cluster_name,
            )
            if not kubeconfigs.kubeconfigs:
                logger.warning(
                    "AzureAksAdapter: list_cluster_user_credentials returned no kubeconfigs"
                )
                self._loaded = False
                return
            raw = kubeconfigs.kubeconfigs[0].value
            if isinstance(raw, bytes):
                # The SDK returns raw bytes (YAML payload, already
                # decoded). Some older versions returned a b64 string;
                # try both shapes.
                try:
                    decoded = base64.b64decode(raw)
                except Exception:
                    decoded = raw
            else:
                try:
                    decoded = base64.b64decode(raw)
                except Exception:
                    decoded = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AzureAksAdapter list_cluster_user_credentials failed: %s", exc)
            self._loaded = False
            return

        # Write kubeconfig to a temp file and load through the standard
        # kubernetes loader — that handles every cluster / context /
        # auth-exec quirk Azure's kubeconfig may carry.
        kc_file = tempfile.NamedTemporaryFile(
            mode="wb", suffix="-aks-kubeconfig.yaml", delete=False
        )
        try:
            kc_file.write(decoded)
            kc_file.flush()
        finally:
            kc_file.close()

        try:
            k8s.config.load_kube_config(config_file=kc_file.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AzureAksAdapter load_kube_config failed: %s", exc)
            self._loaded = False
            return

        self._loaded = True
        self._k8s_module = k8s
        self._cluster_name = cluster_name
        self._resource_group = resource_group
        self._subscription_id = subscription_id
        logger.info(
            "AzureAksAdapter loaded cluster=%s rg=%s sub=%s",
            cluster_name,
            resource_group,
            subscription_id,
        )

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "cluster_name": self._cluster_name,
                "resource_group": self._resource_group,
                "subscription_id": self._subscription_id,
            }
        )
        return out


__all__ = ["AzureAksAdapter"]
