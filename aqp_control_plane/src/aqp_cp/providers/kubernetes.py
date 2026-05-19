"""Kubernetes :class:`InfrastructureProvider`.

Wraps the official ``kubernetes`` Python client. Supports both
in-cluster (ServiceAccount mounted at ``/var/run/secrets/kubernetes.io``)
and out-of-cluster (kubeconfig path) modes.

Maps:

- :attr:`DeploymentSpec.service_id`      -> Deployment ``metadata.name``
- :attr:`DeploymentSpec.namespace`       -> ``metadata.namespace``
- :attr:`DeploymentSpec.replicas`        -> ``spec.replicas``
- :attr:`DeploymentSpec.image`           -> first container's image
- :attr:`DeploymentSpec.env`             -> first container's env (plain values)
- :attr:`DeploymentSpec.env_from_secrets`-> ``envFrom.secretRef`` entries
- :attr:`ConfigMapPatch.values`          -> ConfigMap ``data`` payload
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
)
from aqp_platform_core.models.health import HealthStatus, ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import register_provider_class

logger = logging.getLogger(__name__)


@register_provider_class("kubernetes", replace=True)
class KubernetesProvider(InfrastructureProvider):
    """Kubernetes provider — production target."""

    provider_kind = ProviderKind.KUBERNETES
    provider_alias = "kubernetes"

    def __init__(
        self,
        kubeconfig_path: str | None = None,
        kube_context: str | None = None,
        default_namespace: str | None = None,
    ) -> None:
        self.kubeconfig_path = kubeconfig_path or os.environ.get(
            "AQP_CP_KUBECONFIG_PATH", ""
        )
        self.kube_context = kube_context or os.environ.get(
            "AQP_CP_KUBE_CONTEXT", ""
        )
        self.default_namespace = default_namespace or os.environ.get(
            "AQP_CP_KUBE_NAMESPACE_DEFAULT", "aqp"
        )
        self._initialised = False

    def _ensure_client(self) -> tuple[Any, Any, Any]:
        """Lazy-load the kubernetes client. Returns (CoreV1, AppsV1, CustomObjects)."""
        try:
            from kubernetes import client, config  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "kubernetes SDK not installed (pip install 'aqp-control-plane[kubernetes]')",
                provider=self.provider_alias,
            ) from exc

        if not self._initialised:
            try:
                if self.kubeconfig_path:
                    config.load_kube_config(
                        config_file=self.kubeconfig_path,
                        context=self.kube_context or None,
                    )
                else:
                    try:
                        config.load_incluster_config()
                    except config.ConfigException:
                        config.load_kube_config(
                            context=self.kube_context or None,
                        )
                self._initialised = True
            except Exception as exc:  # noqa: BLE001
                raise InfrastructureProviderUnavailable(
                    f"kubernetes config load failed: {exc}",
                    provider=self.provider_alias,
                ) from exc

        return client.CoreV1Api(), client.AppsV1Api(), client.CustomObjectsApi()

    # ---- Health ------------------------------------------------------

    async def health(self) -> ProviderHealth:
        try:
            core, _apps, _co = await asyncio.to_thread(self._ensure_client)
            ns_list = await asyncio.to_thread(core.list_namespace, timeout_seconds=5)
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.OK,
                available=True,
                last_probe_at=_now(),
                metadata={
                    "namespaces_visible": len(ns_list.items),
                    "default_namespace": self.default_namespace,
                },
            )
        except InfrastructureProviderUnavailable as exc:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=_now(),
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.DEGRADED,
                available=False,
                last_probe_at=_now(),
                error=str(exc),
            )

    # ---- Lifecycle ---------------------------------------------------

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        _core, apps, _co = await asyncio.to_thread(self._ensure_client)
        namespace = spec.namespace or self.default_namespace
        body = _spec_to_deployment(spec, namespace=namespace)

        def _apply() -> None:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]

            try:
                apps.read_namespaced_deployment(name=spec.service_id, namespace=namespace)
                apps.patch_namespaced_deployment(
                    name=spec.service_id, namespace=namespace, body=body
                )
            except ApiException as exc:
                if exc.status == 404:
                    apps.create_namespaced_deployment(namespace=namespace, body=body)
                    return
                raise

        try:
            await asyncio.to_thread(_apply)
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes start failed for {spec.service_id}: {exc}",
                code="start_failed",
                provider=self.provider_alias,
            ) from exc

        return await self.status(spec.service_id, namespace=namespace)

    async def stop(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        return await self.scale(service_id, 0, namespace=namespace)

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        _core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        body = {"spec": {"replicas": int(replicas)}}
        try:
            await asyncio.to_thread(
                apps.patch_namespaced_deployment_scale,
                name=service_id,
                namespace=ns,
                body=body,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes scale failed for {service_id}: {exc}",
                code="scale_failed",
                provider=self.provider_alias,
            ) from exc
        return await self.status(service_id, namespace=ns)

    async def status(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        _core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        try:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]

            try:
                dep = await asyncio.to_thread(
                    apps.read_namespaced_deployment_status,
                    name=service_id,
                    namespace=ns,
                )
            except ApiException as exc:
                if exc.status == 404:
                    return DeploymentStatus(
                        service_id=service_id,
                        provider=self.provider_alias,
                        phase=DeploymentLifecyclePhase.UNKNOWN,
                        namespace=ns,
                    )
                raise
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes status failed for {service_id}: {exc}",
                code="status_failed",
                provider=self.provider_alias,
            ) from exc

        return _deployment_to_status(dep, provider_alias=self.provider_alias)

    async def list_deployments(
        self,
        *,
        namespace: str | None = None,
    ) -> list[DeploymentStatus]:
        _core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        try:
            deps = await asyncio.to_thread(apps.list_namespaced_deployment, namespace=ns)
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes list_deployments failed: {exc}",
                code="list_failed",
                provider=self.provider_alias,
            ) from exc
        return [
            _deployment_to_status(d, provider_alias=self.provider_alias)
            for d in deps.items
        ]

    # ---- Config ------------------------------------------------------

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> ServiceConfig:
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        cm_name = f"{service_id}-config"
        try:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]

            try:
                cm = await asyncio.to_thread(
                    core.read_namespaced_config_map, name=cm_name, namespace=ns
                )
            except ApiException as exc:
                if exc.status == 404:
                    return ServiceConfig(service_id=service_id, values={})
                raise
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes get_config failed: {exc}",
                code="get_config_failed",
                provider=self.provider_alias,
            ) from exc
        data = cm.data or {}
        return ServiceConfig(
            service_id=service_id,
            values={k: str(v) for k, v in data.items()},
            raw={"metadata": {"name": cm_name, "namespace": ns}},
        )

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = self.default_namespace
        cm_name = f"{patch.service_id}-config"
        # Merge values + delete_keys -> new data dict.
        try:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]
            from kubernetes import client  # type: ignore[import-not-found]

            try:
                existing = await asyncio.to_thread(
                    core.read_namespaced_config_map, name=cm_name, namespace=ns
                )
                merged = dict(existing.data or {})
            except ApiException as exc:
                if exc.status == 404:
                    merged = {}
                else:
                    raise
            for key in patch.delete_keys:
                merged.pop(key, None)
            for key, value in patch.values.items():
                merged[key] = str(value)
            body = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=cm_name, namespace=ns),
                data=merged,
            )
            try:
                await asyncio.to_thread(
                    core.replace_namespaced_config_map,
                    name=cm_name,
                    namespace=ns,
                    body=body,
                )
            except ApiException as exc:
                if exc.status == 404:
                    await asyncio.to_thread(
                        core.create_namespaced_config_map, namespace=ns, body=body
                    )
                else:
                    raise
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes apply_config failed: {exc}",
                code="apply_config_failed",
                provider=self.provider_alias,
            ) from exc

        if patch.trigger_restart:
            # Rolling restart via annotation bump.
            ts = _now().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "aqp.internal/restarted-at": ts,
                            }
                        }
                    }
                }
            }
            try:
                await asyncio.to_thread(
                    apps.patch_namespaced_deployment,
                    name=patch.service_id,
                    namespace=ns,
                    body=body,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("kubernetes rolling-restart annotation failed: %s", exc)
        return True

    # ---- Telemetry ---------------------------------------------------

    async def stream_metrics(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float = 10.0,
    ) -> AsyncIterator[MetricPoint]:
        _core, _apps, custom = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace

        while True:
            try:
                metrics = await asyncio.to_thread(
                    custom.list_namespaced_custom_object,
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=ns,
                    plural="pods",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "kubernetes metrics server unreachable for service=%s ns=%s: %s",
                    service_id,
                    ns,
                    exc,
                )
                await asyncio.sleep(interval_seconds)
                continue

            ts = _now()
            for pod_metric in metrics.get("items", []):
                pod_name = pod_metric.get("metadata", {}).get("name", "")
                # Match pods named like the deployment (app=service_id).
                if not pod_name.startswith(service_id):
                    continue
                for container in pod_metric.get("containers", []):
                    usage = container.get("usage", {})
                    cpu_str = usage.get("cpu", "0n")
                    mem_str = usage.get("memory", "0Ki")
                    yield MetricPoint(
                        service_id=service_id,
                        provider=self.provider_alias,
                        metric="cpu_usage",
                        value=_parse_quantity_cpu(cpu_str),
                        unit="cores",
                        timestamp=ts,
                        labels={"pod": pod_name, "container": container.get("name", "")},
                    )
                    yield MetricPoint(
                        service_id=service_id,
                        provider=self.provider_alias,
                        metric="memory_used_bytes",
                        value=_parse_quantity_memory(mem_str),
                        unit="bytes",
                        timestamp=ts,
                        labels={"pod": pod_name, "container": container.get("name", "")},
                    )
            await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _spec_to_deployment(spec: DeploymentSpec, *, namespace: str) -> dict[str, Any]:
    container: dict[str, Any] = {
        "name": spec.service_id,
        "image": spec.image,
        "env": [{"name": k, "value": str(v)} for k, v in spec.env.items()],
        "ports": [{"containerPort": p} for p in spec.ports],
    }
    if spec.command:
        container["command"] = list(spec.command)
    if spec.args:
        container["args"] = list(spec.args)
    if spec.env_from_secrets:
        container["envFrom"] = [
            {"secretRef": {"name": secret_name}} for secret_name in spec.env_from_secrets
        ]
    if spec.health_check_path:
        port = spec.health_check_port or (spec.ports[0] if spec.ports else 80)
        container["readinessProbe"] = {
            "httpGet": {"path": spec.health_check_path, "port": port},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        }
        container["livenessProbe"] = {
            "httpGet": {"path": spec.health_check_path, "port": port},
            "initialDelaySeconds": 30,
            "periodSeconds": 30,
        }
    resources: dict[str, Any] = {}
    if spec.resources.cpu_request or spec.resources.memory_request:
        resources["requests"] = {}
        if spec.resources.cpu_request:
            resources["requests"]["cpu"] = spec.resources.cpu_request
        if spec.resources.memory_request:
            resources["requests"]["memory"] = spec.resources.memory_request
    if spec.resources.cpu_limit or spec.resources.memory_limit:
        resources["limits"] = {}
        if spec.resources.cpu_limit:
            resources["limits"]["cpu"] = spec.resources.cpu_limit
        if spec.resources.memory_limit:
            resources["limits"]["memory"] = spec.resources.memory_limit
    if resources:
        container["resources"] = resources

    labels = {"app": spec.service_id, **spec.labels}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": spec.service_id,
            "namespace": namespace,
            "labels": labels,
        },
        "spec": {
            "replicas": int(spec.replicas),
            "selector": {"matchLabels": {"app": spec.service_id}},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [container],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                    },
                },
            },
        },
    }


def _deployment_to_status(deployment: Any, *, provider_alias: str) -> DeploymentStatus:
    md = getattr(deployment, "metadata", None)
    spec = getattr(deployment, "spec", None)
    status = getattr(deployment, "status", None)

    name = getattr(md, "name", "") if md else ""
    namespace = getattr(md, "namespace", "") if md else None
    replicas_desired = int(getattr(spec, "replicas", 0) or 0) if spec else 0
    replicas_ready = int(getattr(status, "ready_replicas", 0) or 0) if status else 0

    if status is None:
        phase = DeploymentLifecyclePhase.UNKNOWN
    elif replicas_desired == 0:
        phase = DeploymentLifecyclePhase.STOPPED
    elif replicas_ready == replicas_desired:
        phase = DeploymentLifecyclePhase.RUNNING
    elif replicas_ready > 0:
        phase = DeploymentLifecyclePhase.DEGRADED
    else:
        phase = DeploymentLifecyclePhase.STARTING

    image = None
    try:
        containers = spec.template.spec.containers if spec else []
        if containers:
            image = containers[0].image
    except AttributeError:
        pass

    conditions: list[dict[str, Any]] = []
    if status and getattr(status, "conditions", None):
        conditions = [
            {
                "type": c.type,
                "status": c.status,
                "reason": getattr(c, "reason", None),
                "message": getattr(c, "message", None),
            }
            for c in status.conditions
        ]

    return DeploymentStatus(
        service_id=name,
        provider=provider_alias,
        phase=phase,
        replicas_desired=replicas_desired,
        replicas_ready=replicas_ready,
        image=image,
        namespace=namespace,
        last_transition_at=_now(),
        conditions=conditions,
    )


def _parse_quantity_cpu(value: str) -> float:
    """Convert a Kubernetes CPU quantity string to cores.

    Examples: ``"500m"`` -> 0.5, ``"2"`` -> 2.0, ``"100n"`` -> 0.0000001.
    """
    s = str(value).strip()
    if not s:
        return 0.0
    if s.endswith("m"):
        return float(s[:-1]) / 1000.0
    if s.endswith("u"):
        return float(s[:-1]) / 1_000_000.0
    if s.endswith("n"):
        return float(s[:-1]) / 1_000_000_000.0
    return float(s)


def _parse_quantity_memory(value: str) -> float:
    """Convert a Kubernetes memory quantity string to bytes."""
    s = str(value).strip()
    units = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for suffix, multiplier in units.items():
        if s.endswith(suffix):
            return float(s[: -len(suffix)]) * multiplier
    return float(s)


__all__ = ["KubernetesProvider"]
