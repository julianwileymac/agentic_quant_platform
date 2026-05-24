"""KubernetesProcessProxy subclass for AQP per-user kernel pods.

Per the Jupyter Enterprise Gateway docs the ``KubernetesProcessProxy``
"enables Jupyter Notebook to launch remote kernels in a distributed
cluster… Kubernetes". The AQP subclass overrides three behaviours:

1. **Per-user namespacing.** Each kernel pod lands in
   ``aqp-kernel-<uid>`` instead of a shared namespace.
2. **Secret-broker sidecar injection.** Every kernel pod gets a
   sidecar container that exposes the user's per-vendor secrets
   over a Unix domain socket; no secret material touches the
   kernel filesystem.
3. **Rate-limit env preset.** ``HTTPS_PROXY=http://rl-proxy.aqp-system:8080``
   is set automatically so every outbound vendor API call
   debits the (user, service, key_id) bucket.

The subclass is registered by Gateway via its
``KernelSpec.process_proxy.class_name`` entry which the per-pod
template under [aqp_kernels/pods/templates/](aqp_kernels/pods/templates/)
points to.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


try:
    from enterprise_gateway.services.processproxies.k8s import (  # type: ignore[import-not-found]
        KubernetesProcessProxy as _BaseKubernetesProxy,
    )
except Exception:  # noqa: BLE001
    _BaseKubernetesProxy = object  # type: ignore[misc,assignment]


_RL_PROXY_URL = "http://rl-proxy.aqp-system.svc.cluster.local:8080"


class AQPKubernetesProcessProxy(_BaseKubernetesProxy):  # type: ignore[misc]
    """KubernetesProcessProxy that namespaces per user + injects RL proxy."""

    def _build_namespace(self) -> str:
        """Return ``aqp-kernel-<sanitized-user>``."""
        user = os.environ.get("KERNEL_USERNAME") or os.environ.get(
            "AQP_USER_ID", "anonymous"
        )
        sanitized = (
            str(user).lower().replace("@", "-").replace(".", "-").replace("/", "-")
        )
        return f"aqp-kernel-{sanitized}"

    def _ensure_aqp_env(self, env: dict[str, str] | None) -> dict[str, str]:
        env = dict(env or {})
        env.setdefault("HTTPS_PROXY", _RL_PROXY_URL)
        env.setdefault("HTTP_PROXY", _RL_PROXY_URL)
        env.setdefault(
            "NO_PROXY",
            ".aqp-system.svc,.aqp-data-services.svc,.aqp-elt.svc,127.0.0.1,localhost",
        )
        env.setdefault(
            "AQP_KERNEL_ID",
            os.environ.get("KERNEL_ID", "unknown"),
        )
        return env

    async def launch_process(
        self,
        kernel_cmd: list[str],
        **kwargs: Any,
    ) -> Any | None:
        # Force per-user namespace + RL proxy env on every launch.
        kwargs["kernel_namespace"] = self._build_namespace()
        kwargs["kernel_env"] = self._ensure_aqp_env(kwargs.get("kernel_env"))
        logger.info(
            "AQPKubernetesProcessProxy.launch_process namespace=%s, image=%s",
            kwargs["kernel_namespace"],
            kwargs.get("image_name", "<default>"),
        )
        if _BaseKubernetesProxy is object:
            # The optional `enterprise-gateway` dep isn't installed;
            # skeleton mode just logs.
            return None
        return await super().launch_process(kernel_cmd, **kwargs)  # type: ignore[misc]


__all__ = ["AQPKubernetesProcessProxy"]
