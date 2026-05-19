"""Cloudflare :class:`InfrastructureProvider` — Zero Trust tunnels + DNS + Access apps.

Service IDs map to Cloudflare Tunnel names (``cfd_tunnel`` resources).
``DeploymentSpec`` fields are translated:

- ``service_id``      -> tunnel name (created on first ``start``)
- ``namespace``       -> Cloudflare account_id (defaults to settings)
- ``env``             -> tunnel ingress rules (``hostname``/``service``
  pairs read from ``AQP_CF_INGRESS_*`` env vars or the spec metadata
  block).

The Management Engine subagent rule
(``.cursor/rules/aqp-management-engine.mdc``) forbids logging tunnel
secrets, API tokens, or the raw Cloudflare-Access JWT — this provider
never persists secret material to the audit ledger.

Reference: `Cloudflare Python SDK
<https://github.com/cloudflare/cloudflare-python>`_ + the
:class:`aqp.cloudflare.CloudflareEdgeAdapter` shared by the in-AQP
:class:`aqp.api.routes.cloudflare` router.
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
from aqp_platform_core.models.workloads import SecretRotationResult
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import register_provider_class

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_provider_class("cloudflare", replace=True)
class CloudflareProvider(InfrastructureProvider):
    """Cloudflare Zero Trust tunnel / DNS / Access provider.

    Backed by the official ``cloudflare`` Python SDK. Credentials
    resolve via :class:`aqp_platform_core.credentials.CredentialResolver`
    or env vars (``CLOUDFLARE_API_TOKEN`` + ``CLOUDFLARE_ACCOUNT_ID``).

    Workload-action mapping:

    - ``start``  -> ``zero_trust.tunnels.create`` (idempotent on name)
    - ``stop``   -> ``zero_trust.tunnels.cloudflared.configurations`` clears ingress
    - ``scale``  -> No-op for tunnels (cloudflared replicas live in K8s)
    - ``restart``-> Rotate the tunnel's configuration (forces cloudflared reload)
    - ``status`` -> Read the tunnel's connections + last-active timestamp
    - ``rotate_secret`` -> Mint a fresh tunnel secret (``tunnel_secret``)
    - ``exec`` / ``tail_logs`` -> raise unavailable (Cloudflare has no shell)
    """

    provider_kind = ProviderKind.CLOUDFLARE
    provider_alias = "cloudflare"

    def __init__(
        self,
        api_token: str | None = None,
        account_id: str | None = None,
    ) -> None:
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN", "")
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_token:
            raise InfrastructureProviderUnavailable(
                "Cloudflare API token missing (set CLOUDFLARE_API_TOKEN or wire via CredentialResolver)",
                provider=self.provider_alias,
            )
        if not self._account_id:
            raise InfrastructureProviderUnavailable(
                "Cloudflare account id missing (set CLOUDFLARE_ACCOUNT_ID)",
                provider=self.provider_alias,
            )
        try:
            from cloudflare import Cloudflare  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "cloudflare SDK not installed (pip install 'cloudflare>=4.0')",
                provider=self.provider_alias,
            ) from exc
        self._client = Cloudflare(api_token=self._api_token)
        return self._client

    # ---- Health ------------------------------------------------------

    async def health(self) -> ProviderHealth:
        if not self._api_token:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=_now(),
                error="CLOUDFLARE_API_TOKEN not set",
            )
        try:
            client = await asyncio.to_thread(self._ensure_client)
            # Single cheap call: verify the token's own scopes.
            ident = await asyncio.to_thread(client.user.tokens.verify)
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.OK,
                available=True,
                last_probe_at=_now(),
                metadata={
                    "account_id": self._account_id,
                    "token_id": getattr(ident, "id", None),
                    "token_status": getattr(ident, "status", None),
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
        """Create-or-update the named tunnel."""
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(spec.service_id)
        if existing is not None:
            tunnel_id = getattr(existing, "id", None)
        else:
            try:
                created = await asyncio.to_thread(
                    client.zero_trust.tunnels.create,
                    account_id=self._account_id,
                    name=spec.service_id,
                    config_src="cloudflare",  # remotely-managed (no local YAML).
                )
            except Exception as exc:  # noqa: BLE001
                raise InfrastructureProviderError(
                    f"cloudflare tunnel create failed: {exc}",
                    code="start_failed",
                    provider=self.provider_alias,
                ) from exc
            tunnel_id = getattr(created, "id", None)
        return await self.status(spec.service_id, namespace=spec.namespace)

    async def stop(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Disable tunnel ingress (clears the public hostname routes)."""
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(service_id)
        if existing is None:
            return DeploymentStatus(
                service_id=service_id,
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.UNKNOWN,
                namespace=self._account_id,
            )
        tunnel_id = existing.id
        try:
            await asyncio.to_thread(
                client.zero_trust.tunnels.cloudflared.configurations.update,
                tunnel_id=tunnel_id,
                account_id=self._account_id,
                config={"ingress": []},
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare tunnel stop failed: {exc}",
                code="stop_failed",
                provider=self.provider_alias,
            ) from exc
        return await self.status(service_id, namespace=namespace)

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Cloudflare tunnels scale via cloudflared replica count (K8s side).

        The Management Engine treats this as a no-op when the operator
        asks for ``replicas >= 1`` (cloudflared sidecar is owned by the
        ``KubernetesProvider`` in the same control plane). When
        ``replicas == 0`` we delegate to :meth:`stop`.
        """
        if replicas == 0:
            return await self.stop(service_id, namespace=namespace)
        return await self.status(service_id, namespace=namespace)

    async def restart(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Force cloudflared to reload by re-applying the current config."""
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(service_id)
        if existing is None:
            raise InfrastructureProviderError(
                f"tunnel {service_id!r} not found",
                code="not_found",
                provider=self.provider_alias,
            )
        tunnel_id = existing.id
        try:
            cfg = await asyncio.to_thread(
                client.zero_trust.tunnels.cloudflared.configurations.get,
                tunnel_id=tunnel_id,
                account_id=self._account_id,
            )
            # Round-trip the config — the daemon picks it up on its
            # next heartbeat (typically <5 s).
            await asyncio.to_thread(
                client.zero_trust.tunnels.cloudflared.configurations.update,
                tunnel_id=tunnel_id,
                account_id=self._account_id,
                config=getattr(cfg, "config", {}),
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare tunnel restart failed: {exc}",
                code="restart_failed",
                provider=self.provider_alias,
            ) from exc
        return await self.status(service_id, namespace=namespace)

    async def status(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        existing = await self._find_tunnel(service_id)
        if existing is None:
            return DeploymentStatus(
                service_id=service_id,
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.UNKNOWN,
                namespace=self._account_id,
            )
        # Healthy tunnel: ``status`` field is ``"healthy"``; degraded otherwise.
        tunnel_status = str(getattr(existing, "status", "") or "").lower()
        phase = (
            DeploymentLifecyclePhase.RUNNING
            if tunnel_status == "healthy"
            else DeploymentLifecyclePhase.DEGRADED
            if tunnel_status
            else DeploymentLifecyclePhase.UNKNOWN
        )
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=phase,
            replicas_desired=1,
            replicas_ready=1 if phase == DeploymentLifecyclePhase.RUNNING else 0,
            namespace=self._account_id,
            last_transition_at=_now(),
            conditions=[
                {
                    "type": "TunnelStatus",
                    "status": tunnel_status,
                    "id": getattr(existing, "id", None),
                    "name": getattr(existing, "name", None),
                }
            ],
        )

    async def list_deployments(
        self,
        *,
        namespace: str | None = None,
    ) -> list[DeploymentStatus]:
        client = await asyncio.to_thread(self._ensure_client)
        try:
            tunnels = await asyncio.to_thread(
                client.zero_trust.tunnels.list, account_id=self._account_id
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare tunnels list failed: {exc}",
                code="list_failed",
                provider=self.provider_alias,
            ) from exc
        out: list[DeploymentStatus] = []
        for tunnel in self._iter_paginated(tunnels):
            name = getattr(tunnel, "name", "")
            tunnel_status = str(getattr(tunnel, "status", "") or "").lower()
            phase = (
                DeploymentLifecyclePhase.RUNNING
                if tunnel_status == "healthy"
                else DeploymentLifecyclePhase.DEGRADED
                if tunnel_status
                else DeploymentLifecyclePhase.UNKNOWN
            )
            out.append(
                DeploymentStatus(
                    service_id=name,
                    provider=self.provider_alias,
                    phase=phase,
                    replicas_desired=1,
                    replicas_ready=1
                    if phase == DeploymentLifecyclePhase.RUNNING
                    else 0,
                    namespace=self._account_id,
                    last_transition_at=_now(),
                    raw={"id": getattr(tunnel, "id", None)},
                )
            )
        return out

    # ---- Secrets / config -------------------------------------------

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        namespace: str | None = None,
    ) -> SecretRotationResult:
        """Rotate the tunnel's secret (``tunnel_secret``).

        Per Cloudflare's API, rotating the secret requires deleting the
        tunnel and recreating it. The Management Engine surfaces this
        as ``not_implemented`` until operators opt-in via
        ``AQP_CP_CLOUDFLARE_DESTRUCTIVE_ROTATION=1``; in that case
        callers MUST schedule cloudflared rollouts immediately
        afterwards or the public edge goes dark.
        """
        if os.environ.get(
            "AQP_CP_CLOUDFLARE_DESTRUCTIVE_ROTATION", ""
        ).lower() not in ("1", "true", "yes"):
            raise InfrastructureProviderUnavailable(
                "Cloudflare tunnel secret rotation is destructive (delete+recreate). "
                "Set AQP_CP_CLOUDFLARE_DESTRUCTIVE_ROTATION=1 to opt in.",
                provider=self.provider_alias,
            )
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(service_id)
        if existing is None:
            raise InfrastructureProviderError(
                f"tunnel {service_id!r} not found",
                code="not_found",
                provider=self.provider_alias,
            )
        tunnel_id = existing.id
        try:
            await asyncio.to_thread(
                client.zero_trust.tunnels.delete,
                tunnel_id=tunnel_id,
                account_id=self._account_id,
            )
            recreated = await asyncio.to_thread(
                client.zero_trust.tunnels.create,
                account_id=self._account_id,
                name=service_id,
                config_src=getattr(existing, "config_src", "cloudflare"),
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare tunnel rotation failed: {exc}",
                code="rotate_secret_failed",
                provider=self.provider_alias,
            ) from exc
        return SecretRotationResult(
            service_id=service_id,
            secret_name=secret_name,
            backend="cloudflare_zero_trust",
            rotation_id=f"cf-{tunnel_id}-{int(time.time())}",
            new_version=getattr(recreated, "id", None),
            rotated_at=_now(),
            metadata={
                "account_id": self._account_id,
                "warning": "destructive rotation — cloudflared must reconnect",
            },
        )

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> ServiceConfig:
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(service_id)
        if existing is None:
            raise InfrastructureProviderError(
                f"tunnel {service_id!r} not found",
                code="not_found",
                provider=self.provider_alias,
            )
        cfg = await asyncio.to_thread(
            client.zero_trust.tunnels.cloudflared.configurations.get,
            tunnel_id=existing.id,
            account_id=self._account_id,
        )
        raw = getattr(cfg, "config", {}) or {}
        ingress = raw.get("ingress", []) if isinstance(raw, dict) else []
        # Flatten ingress rules into a values dict (read-only display).
        values: dict[str, str] = {}
        for idx, rule in enumerate(ingress):
            if not isinstance(rule, dict):
                continue
            host = str(rule.get("hostname") or f"<catchall-{idx}>")
            values[host] = str(rule.get("service", ""))
        return ServiceConfig(service_id=service_id, values=values, raw=raw)

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        """Apply an ingress patch — ``values`` keyed by hostname -> service URL."""
        client = await asyncio.to_thread(self._ensure_client)
        existing = await self._find_tunnel(patch.service_id)
        if existing is None:
            raise InfrastructureProviderError(
                f"tunnel {patch.service_id!r} not found",
                code="not_found",
                provider=self.provider_alias,
            )
        ingress = [
            {"hostname": host, "service": svc}
            for host, svc in patch.values.items()
            if host not in patch.delete_keys
        ]
        # Always end with a catch-all per Cloudflare's docs.
        ingress.append({"service": "http_status:404"})
        try:
            await asyncio.to_thread(
                client.zero_trust.tunnels.cloudflared.configurations.update,
                tunnel_id=existing.id,
                account_id=self._account_id,
                config={"ingress": ingress},
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare apply_config failed: {exc}",
                code="apply_config_failed",
                provider=self.provider_alias,
            ) from exc
        return True

    # ---- Telemetry ---------------------------------------------------

    async def stream_metrics(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float = 10.0,
    ) -> AsyncIterator[MetricPoint]:
        # Cloudflare exposes analytics via GraphQL; the in-AQP
        # CloudflareEdgeAdapter handles richer queries. The CP-side
        # provider keeps stream_metrics minimal and yields one point
        # per poll (tunnel up/down).
        while True:
            try:
                status_obj = await self.status(service_id)
                value = 1.0 if status_obj.phase == DeploymentLifecyclePhase.RUNNING else 0.0
                yield MetricPoint(
                    service_id=service_id,
                    provider=self.provider_alias,
                    metric="tunnel_up",
                    value=value,
                    unit="bool",
                    timestamp=_now(),
                    labels={"account_id": self._account_id or ""},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("cloudflare metrics poll failed: %s", exc)
            await asyncio.sleep(interval_seconds)

    # ---- Internals ---------------------------------------------------

    async def _find_tunnel(self, name: str) -> Any | None:
        client = await asyncio.to_thread(self._ensure_client)
        try:
            tunnels = await asyncio.to_thread(
                client.zero_trust.tunnels.list,
                account_id=self._account_id,
                name=name,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"cloudflare tunnels lookup failed: {exc}",
                code="lookup_failed",
                provider=self.provider_alias,
            ) from exc
        for tunnel in self._iter_paginated(tunnels):
            if getattr(tunnel, "name", "") == name:
                return tunnel
        return None

    @staticmethod
    def _iter_paginated(page):
        """Walk a Cloudflare SDK pager — accepts list-like or page-iterator."""
        try:
            yield from page
        except TypeError:
            # Older SDK versions return a SyncPaginator that needs .iter.
            for item in getattr(page, "iter", lambda: [])():
                yield item


__all__ = ["CloudflareProvider"]
