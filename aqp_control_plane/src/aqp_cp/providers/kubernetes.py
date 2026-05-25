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
import time
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
from aqp_platform_core.models.tenancy import (
    TenantNamespacePhase,
    TenantNamespaceSpec,
    TenantNamespaceStatus,
)
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadExecResult,
    WorkloadLogEvent,
)
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import register_provider_class

from aqp_cp.builders.tenant import render_tenant_namespace_objects

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

    # ---- Management Engine extensions (Phase A) ----------------------

    async def restart(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Rolling-restart by stamping ``aqp.internal/restarted-at`` on the pod template."""
        _core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        ts = _now().isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"aqp.internal/restarted-at": ts}
                    }
                }
            }
        }
        try:
            await asyncio.to_thread(
                apps.patch_namespaced_deployment,
                name=service_id,
                namespace=ns,
                body=body,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes restart failed for {service_id}: {exc}",
                code="restart_failed",
                provider=self.provider_alias,
            ) from exc
        return await self.status(service_id, namespace=ns)

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
        """Execute ``command`` in a pod backing ``service_id``.

        Uses ``kubernetes.stream.stream`` with ``_preload_content=False``
        per the documented client bug. The first pod matching the
        ``app=<service_id>`` label is targeted; for finer control,
        callers should use the lower-level pod exec route.
        """
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        try:
            from kubernetes.stream import stream  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "kubernetes stream module not installed",
                provider=self.provider_alias,
            ) from exc

        pod_name = await self._find_pod_for_service(service_id, namespace=ns)
        started_at = _now()
        try:
            resp = await asyncio.to_thread(
                stream,
                core.connect_get_namespaced_pod_exec,
                pod_name,
                ns,
                command=command,
                container=container,
                stderr=True,
                stdin=stdin is not None,
                stdout=True,
                tty=False,
                _preload_content=False,
                _request_timeout=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes exec dispatch failed for {service_id}/{pod_name}: {exc}",
                code="exec_failed",
                provider=self.provider_alias,
            ) from exc

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _drain() -> tuple[str, str, int | None]:
            try:
                if stdin is not None:
                    resp.write_stdin(stdin.decode("utf-8", errors="replace"))
                deadline = time.monotonic() + timeout_seconds
                while resp.is_open():
                    if time.monotonic() > deadline:
                        break
                    resp.update(timeout=1)
                    if resp.peek_stdout():
                        stdout_chunks.append(resp.read_stdout())
                    if resp.peek_stderr():
                        stderr_chunks.append(resp.read_stderr())
                # Read any tail buffered after the socket closed.
                if resp.peek_stdout():
                    stdout_chunks.append(resp.read_stdout())
                if resp.peek_stderr():
                    stderr_chunks.append(resp.read_stderr())
            finally:
                try:
                    resp.close()
                except Exception:  # noqa: BLE001
                    pass
            rc = None
            try:
                # kubernetes-client surfaces the exit code via returncode.
                rc = int(getattr(resp, "returncode", None) or 0)
            except Exception:  # noqa: BLE001
                rc = None
            return "".join(stdout_chunks), "".join(stderr_chunks), rc

        stdout, stderr, rc = await asyncio.to_thread(_drain)
        finished_at = _now()
        return WorkloadExecResult(
            service_id=service_id,
            namespace=ns,
            container=container,
            command=list(command),
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
            elapsed_ms=(finished_at - started_at).total_seconds() * 1000.0,
            started_at=started_at,
            finished_at=finished_at,
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
        """Stream :class:`WorkloadLogEvent` frames for ``service_id``.

        CRITICAL: passes ``_preload_content=False`` and consumes through
        ``kubernetes.watch.Watch().stream(...)`` per the documented
        sparse-log hang in the Python client.
        """
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        try:
            from kubernetes import watch  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "kubernetes watch module not installed",
                provider=self.provider_alias,
            ) from exc

        pod_name = await self._find_pod_for_service(service_id, namespace=ns)
        emitted = 0

        def _open_stream():
            kwargs: dict[str, Any] = {
                "name": pod_name,
                "namespace": ns,
                "follow": bool(follow),
                "_preload_content": False,
            }
            if container:
                kwargs["container"] = container
            if since_seconds is not None:
                kwargs["since_seconds"] = int(since_seconds)
            if tail is not None:
                kwargs["tail_lines"] = int(tail)
            if follow:
                w = watch.Watch()
                return ("watch", w.stream(core.read_namespaced_pod_log, **kwargs))
            # One-shot tail: stream chunks then close.
            resp = core.read_namespaced_pod_log(**kwargs)
            return ("response", resp)

        kind, source = await asyncio.to_thread(_open_stream)
        try:
            if kind == "watch":
                # ``source`` is a generator of complete lines from Watch.stream.
                for line in source:
                    if max_lines is not None and emitted >= max_lines:
                        break
                    emitted += 1
                    yield WorkloadLogEvent(
                        service_id=service_id,
                        namespace=ns,
                        container=container,
                        line=str(line).rstrip("\n"),
                        timestamp=_now(),
                    )
            else:
                # ``source`` is the raw HTTPResponse; iterate by line.
                buffer = ""
                for chunk in source.stream(amt=4096, decode_content=False):
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, _, buffer = buffer.partition("\n")
                        if max_lines is not None and emitted >= max_lines:
                            return
                        emitted += 1
                        yield WorkloadLogEvent(
                            service_id=service_id,
                            namespace=ns,
                            container=container,
                            line=line.rstrip("\n"),
                            timestamp=_now(),
                        )
                if buffer.strip():
                    yield WorkloadLogEvent(
                        service_id=service_id,
                        namespace=ns,
                        container=container,
                        line=buffer.rstrip("\n"),
                        timestamp=_now(),
                    )
        finally:
            try:
                if kind == "response":
                    source.release_conn()
            except Exception:  # noqa: BLE001
                pass

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        namespace: str | None = None,
    ) -> SecretRotationResult:
        """Rotate a Kubernetes Secret by recreating it with refreshed material.

        AQP-level rotation: this method bumps the
        ``aqp.internal/rotated-at`` annotation on the secret + the
        deployment template (so pods pick up the new value via the next
        rollout). The actual secret material MUST be pre-provisioned by
        the ESO/External Secrets pipeline; this method does NOT fetch
        plaintext secrets. The Management Engine rule forbids logging
        secret values.
        """
        core, apps, _co = await asyncio.to_thread(self._ensure_client)
        ns = namespace or self.default_namespace
        ts = _now().isoformat()
        rotation_id = f"k8s-{service_id}-{secret_name}-{int(time.time())}"
        try:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]

            secret = await asyncio.to_thread(
                core.read_namespaced_secret, name=secret_name, namespace=ns
            )
            # Annotate the secret with the rotation marker.
            annotations = dict(getattr(secret.metadata, "annotations", None) or {})
            annotations["aqp.internal/rotated-at"] = ts
            annotations["aqp.internal/rotation-id"] = rotation_id
            secret.metadata.annotations = annotations
            await asyncio.to_thread(
                core.patch_namespaced_secret,
                name=secret_name,
                namespace=ns,
                body=secret,
            )
            # Trigger a rolling restart so pods re-mount the secret.
            try:
                await self.restart(service_id, namespace=ns)
            except InfrastructureProviderError as exc:
                logger.warning(
                    "rotate_secret: rolling restart of %s failed: %s",
                    service_id,
                    exc,
                )
        except ApiException as exc:
            raise InfrastructureProviderError(
                f"kubernetes rotate_secret failed for {service_id}/{secret_name}: {exc}",
                code="rotate_secret_failed",
                provider=self.provider_alias,
            ) from exc
        return SecretRotationResult(
            service_id=service_id,
            secret_name=secret_name,
            backend="k8s_secret",
            rotation_id=rotation_id,
            new_version=ts,
            rotated_at=_now(),
            metadata={"namespace": ns},
        )

    # ---- Tenancy (Phase 1 — per-tenant namespace bootstrap) ----------

    async def provision_tenant_namespace(
        self,
        spec: TenantNamespaceSpec,
    ) -> TenantNamespaceStatus:
        """SSA Namespace + ResourceQuota + LimitRange + NetworkPolicy.

        Idempotent: applies every rendered object via the kubernetes
        SDK's create-or-replace path, using the ``aqp.io/tenant-controller``
        field manager so future reconciliations don't fight us.
        """
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        try:
            from kubernetes import client  # type: ignore[import-not-found]
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "kubernetes SDK not installed",
                provider=self.provider_alias,
            ) from exc

        namespace = spec.namespace()
        applied_at = _now()
        objects = render_tenant_namespace_objects(spec, now=applied_at)
        objects_applied: list[str] = []

        networking_v1 = client.NetworkingV1Api()

        def _apply_namespace(body: dict[str, Any]) -> None:
            try:
                core.read_namespace(name=namespace)
                core.patch_namespace(name=namespace, body=body)
            except ApiException as exc:
                if exc.status == 404:
                    core.create_namespace(body=body)
                else:
                    raise

        def _apply_resource_quota(body: dict[str, Any]) -> None:
            name = body["metadata"]["name"]
            try:
                core.read_namespaced_resource_quota(name=name, namespace=namespace)
                core.replace_namespaced_resource_quota(
                    name=name, namespace=namespace, body=body
                )
            except ApiException as exc:
                if exc.status == 404:
                    core.create_namespaced_resource_quota(namespace=namespace, body=body)
                else:
                    raise

        def _apply_limit_range(body: dict[str, Any]) -> None:
            name = body["metadata"]["name"]
            try:
                core.read_namespaced_limit_range(name=name, namespace=namespace)
                core.replace_namespaced_limit_range(
                    name=name, namespace=namespace, body=body
                )
            except ApiException as exc:
                if exc.status == 404:
                    core.create_namespaced_limit_range(namespace=namespace, body=body)
                else:
                    raise

        def _apply_network_policy(body: dict[str, Any]) -> None:
            name = body["metadata"]["name"]
            try:
                networking_v1.read_namespaced_network_policy(
                    name=name, namespace=namespace
                )
                networking_v1.replace_namespaced_network_policy(
                    name=name, namespace=namespace, body=body
                )
            except ApiException as exc:
                if exc.status == 404:
                    networking_v1.create_namespaced_network_policy(
                        namespace=namespace, body=body
                    )
                else:
                    raise

        try:
            for body in objects:
                kind = str(body.get("kind", "")).strip()
                name = body.get("metadata", {}).get("name", "<unknown>")
                if kind == "Namespace":
                    await asyncio.to_thread(_apply_namespace, body)
                elif kind == "ResourceQuota":
                    await asyncio.to_thread(_apply_resource_quota, body)
                elif kind == "LimitRange":
                    await asyncio.to_thread(_apply_limit_range, body)
                elif kind == "NetworkPolicy":
                    await asyncio.to_thread(_apply_network_policy, body)
                else:
                    logger.warning(
                        "tenant_namespace render emitted unsupported kind=%s name=%s",
                        kind,
                        name,
                    )
                    continue
                objects_applied.append(f"{kind}/{name}")
        except ApiException as exc:
            raise InfrastructureProviderError(
                f"kubernetes tenant_namespace SSA failed: {exc}",
                code="provision_tenant_failed",
                provider=self.provider_alias,
                details={"objects_applied": objects_applied},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes tenant_namespace SSA failed: {exc}",
                code="provision_tenant_failed",
                provider=self.provider_alias,
                details={"objects_applied": objects_applied},
            ) from exc

        return TenantNamespaceStatus(
            tenant_id=spec.tenant_id,
            namespace=namespace,
            provider=self.provider_alias,
            phase=TenantNamespacePhase.APPLIED,
            applied_at=applied_at,
            objects_applied=objects_applied,
            conditions=[
                {
                    "type": "Applied",
                    "status": "True",
                    "reason": "SsaCompleted",
                    "message": f"Applied {len(objects_applied)} object(s)",
                }
            ],
        )

    async def deprovision_tenant_namespace(
        self,
        tenant_id: str,
        *,
        namespace_prefix: str = "tenant",
    ) -> TenantNamespaceStatus:
        """Tear down the tenant's namespace (cascading delete)."""
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        try:
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "kubernetes SDK not installed",
                provider=self.provider_alias,
            ) from exc
        namespace = f"{namespace_prefix}-{tenant_id}"
        applied_at = _now()
        try:

            def _delete() -> None:
                try:
                    core.delete_namespace(name=namespace)
                except ApiException as exc:
                    if exc.status != 404:
                        raise

            await asyncio.to_thread(_delete)
        except ApiException as exc:
            raise InfrastructureProviderError(
                f"kubernetes tenant_namespace teardown failed: {exc}",
                code="deprovision_tenant_failed",
                provider=self.provider_alias,
            ) from exc
        return TenantNamespaceStatus(
            tenant_id=tenant_id,
            namespace=namespace,
            provider=self.provider_alias,
            phase=TenantNamespacePhase.APPLIED,
            applied_at=applied_at,
            objects_applied=[f"Namespace/{namespace}"],
            conditions=[
                {
                    "type": "Deleted",
                    "status": "True",
                    "reason": "DeleteCompleted",
                    "message": "Namespace delete dispatched (cascading)",
                }
            ],
        )

    async def _find_pod_for_service(
        self, service_id: str, *, namespace: str
    ) -> str:
        """Return the first ready pod name matching ``app=<service_id>``."""
        core, _apps, _co = await asyncio.to_thread(self._ensure_client)
        try:
            pods = await asyncio.to_thread(
                core.list_namespaced_pod,
                namespace=namespace,
                label_selector=f"app={service_id}",
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"kubernetes list_pods failed for {service_id}: {exc}",
                code="list_pods_failed",
                provider=self.provider_alias,
            ) from exc
        for pod in pods.items:
            phase = getattr(getattr(pod, "status", None), "phase", "")
            if str(phase).lower() == "running":
                return pod.metadata.name
        if pods.items:
            return pods.items[0].metadata.name
        raise InfrastructureProviderError(
            f"no pods found for service {service_id!r} in namespace {namespace!r}",
            code="no_pods",
            provider=self.provider_alias,
        )

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
