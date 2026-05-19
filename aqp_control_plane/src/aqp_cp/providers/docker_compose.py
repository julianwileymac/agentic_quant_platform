"""Docker Compose :class:`InfrastructureProvider`.

Drives services declared in a Compose file via the ``docker compose``
subprocess plus the Docker Python SDK for live status / log /
metric introspection.

Maps :attr:`DeploymentSpec.service_id` to the Compose service name.
:attr:`DeploymentSpec.namespace` becomes the Compose project name
(``-p <namespace>``).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
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


@register_provider_class("docker_compose", replace=True)
class DockerComposeProvider(InfrastructureProvider):
    """``docker compose`` provider — local dev + isolated admin overlays."""

    provider_kind = ProviderKind.DOCKER_COMPOSE
    provider_alias = "docker_compose"

    def __init__(
        self,
        compose_file: str | None = None,
        project_name: str | None = None,
        docker_binary: str | None = None,
    ) -> None:
        self.compose_file = compose_file or os.environ.get(
            "AQP_CP_COMPOSE_FILE",
            "deployments/compose/docker-compose.local.yml",
        )
        self.project_name = project_name or os.environ.get(
            "AQP_CP_COMPOSE_PROJECT_NAME", "aqp"
        )
        self.docker_binary = docker_binary or shutil.which("docker") or "docker"

    # ---- Health ------------------------------------------------------

    async def health(self) -> ProviderHealth:
        if shutil.which(self.docker_binary) is None:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=_now(),
                error="docker binary not on PATH",
            )
        if not os.path.exists(self.compose_file):
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.DEGRADED,
                available=False,
                last_probe_at=_now(),
                error=f"compose file {self.compose_file!r} missing",
            )
        # Use `docker info` as the cheapest "is the daemon up?" probe.
        # ``_run`` raises :class:`InfrastructureProviderError` on timeout
        # — translate to a degraded health response instead of bubbling
        # the exception up to the telemetry snapshot route (health() must
        # never raise; that's the whole point of returning ProviderHealth).
        try:
            rc, _stdout, _stderr = await self._run(
                [self.docker_binary, "info"], timeout=5
            )
        except InfrastructureProviderError as exc:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=_now(),
                error=str(exc),
            )
        if rc != 0:
            return ProviderHealth(
                provider=self.provider_alias,
                status=HealthStatus.UNAVAILABLE,
                available=False,
                last_probe_at=_now(),
                error="docker daemon not reachable",
            )
        return ProviderHealth(
            provider=self.provider_alias,
            status=HealthStatus.OK,
            available=True,
            last_probe_at=_now(),
            metadata={
                "compose_file": self.compose_file,
                "project_name": self.project_name,
            },
        )

    # ---- Lifecycle ---------------------------------------------------

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        await self._require_compose()
        args = self._compose_args() + [
            "up",
            "-d",
            "--no-recreate",
            "--scale",
            f"{spec.service_id}={spec.replicas}",
            spec.service_id,
        ]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose up failed for {spec.service_id}: {stderr.strip()}",
                code="start_failed",
                provider=self.provider_alias,
                details={"stdout": stdout, "stderr": stderr, "rc": rc},
            )
        return await self.status(spec.service_id, namespace=spec.namespace)

    async def stop(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        await self._require_compose()
        args = self._compose_args() + ["stop", service_id]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose stop failed for {service_id}: {stderr.strip()}",
                code="stop_failed",
                provider=self.provider_alias,
                details={"stdout": stdout, "stderr": stderr, "rc": rc},
            )
        return await self.status(service_id, namespace=namespace)

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        await self._require_compose()
        args = self._compose_args() + [
            "up",
            "-d",
            "--no-recreate",
            "--scale",
            f"{service_id}={replicas}",
            service_id,
        ]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose scale failed for {service_id}: {stderr.strip()}",
                code="scale_failed",
                provider=self.provider_alias,
                details={"stdout": stdout, "stderr": stderr, "rc": rc},
            )
        return await self.status(service_id, namespace=namespace)

    async def status(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        await self._require_compose()
        args = self._compose_args() + ["ps", "--format", "json", service_id]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            # `docker compose ps` returns 0 with empty stdout when the
            # service has no containers. A non-zero exit means the
            # compose file is unparseable or the service is unknown.
            raise InfrastructureProviderError(
                f"docker compose ps failed for {service_id}: {stderr.strip()}",
                code="status_failed",
                provider=self.provider_alias,
                details={"stdout": stdout, "stderr": stderr, "rc": rc},
            )
        return _parse_ps_output(
            stdout, service_id=service_id, provider_alias=self.provider_alias
        )

    async def list_deployments(
        self,
        *,
        namespace: str | None = None,
    ) -> list[DeploymentStatus]:
        await self._require_compose()
        args = self._compose_args() + ["ps", "--all", "--format", "json"]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose ps failed: {stderr.strip()}",
                code="list_failed",
                provider=self.provider_alias,
                details={"stdout": stdout, "stderr": stderr, "rc": rc},
            )
        services: dict[str, list[dict]] = {}
        for entry in _iter_json_lines(stdout):
            service = entry.get("Service") or entry.get("service") or ""
            services.setdefault(service, []).append(entry)
        out: list[DeploymentStatus] = []
        for service_id, entries in services.items():
            if not service_id:
                continue
            payload = "\n".join(json.dumps(e) for e in entries)
            out.append(
                _parse_ps_output(
                    payload,
                    service_id=service_id,
                    provider_alias=self.provider_alias,
                )
            )
        return out

    # ---- Config ------------------------------------------------------

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> ServiceConfig:
        await self._require_compose()
        args = self._compose_args() + ["config", "--format", "json"]
        rc, stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose config failed: {stderr.strip()}",
                code="get_config_failed",
                provider=self.provider_alias,
                details={"stderr": stderr, "rc": rc},
            )
        try:
            doc = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise InfrastructureProviderError(
                f"docker compose config emitted invalid JSON: {exc}",
                code="get_config_parse",
                provider=self.provider_alias,
            ) from exc
        services = doc.get("services") or {}
        svc = services.get(service_id) or {}
        env = svc.get("environment") or {}
        # `docker compose config` returns env as either a dict or a list
        # of "KEY=VAL" strings; normalise to dict.
        if isinstance(env, list):
            normalised: dict[str, str] = {}
            for entry in env:
                if "=" in entry:
                    key, _, value = entry.partition("=")
                    normalised[key] = value
            env = normalised
        return ServiceConfig(
            service_id=service_id,
            values={str(k): str(v) for k, v in env.items() if not _looks_like_secret(k)},
            raw=svc,
        )

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        # Compose doesn't have a first-class "config patch" — apply by
        # re-running `up -d` with the new environment loaded from
        # whatever env_file the compose file references. The expectation
        # is that the operator regenerates `.env.local` via
        # `make generate-config` BEFORE calling apply_config.
        await self._require_compose()
        if not patch.trigger_restart:
            return True
        args = self._compose_args() + [
            "up",
            "-d",
            "--no-recreate",
            patch.service_id,
        ]
        rc, _stdout, stderr = await self._run(args)
        if rc != 0:
            raise InfrastructureProviderError(
                f"docker compose apply_config failed for {patch.service_id}: {stderr.strip()}",
                code="apply_config_failed",
                provider=self.provider_alias,
            )
        return True

    # ---- Telemetry ---------------------------------------------------

    async def stream_metrics(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        interval_seconds: float = 10.0,
    ) -> AsyncIterator[MetricPoint]:
        await self._require_compose()
        try:
            import docker  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "docker SDK not installed (pip install 'aqp-control-plane[docker_compose]')",
                provider=self.provider_alias,
            ) from exc

        client = docker.from_env()
        try:
            while True:
                containers = client.containers.list(
                    filters={
                        "label": [
                            f"com.docker.compose.service={service_id}",
                            f"com.docker.compose.project={self.project_name}",
                        ]
                    }
                )
                for container in containers:
                    stats = container.stats(stream=False)
                    cpu_pct, mem_pct, mem_used = _parse_docker_stats(stats)
                    ts = _now()
                    yield MetricPoint(
                        service_id=service_id,
                        provider=self.provider_alias,
                        metric="cpu_usage_pct",
                        value=cpu_pct,
                        unit="%",
                        timestamp=ts,
                        labels={"container": container.id[:12]},
                    )
                    yield MetricPoint(
                        service_id=service_id,
                        provider=self.provider_alias,
                        metric="memory_usage_pct",
                        value=mem_pct,
                        unit="%",
                        timestamp=ts,
                        labels={"container": container.id[:12]},
                    )
                    yield MetricPoint(
                        service_id=service_id,
                        provider=self.provider_alias,
                        metric="memory_used_bytes",
                        value=mem_used,
                        unit="bytes",
                        timestamp=ts,
                        labels={"container": container.id[:12]},
                    )
                await asyncio.sleep(interval_seconds)
        finally:
            client.close()

    # ---- Internals ---------------------------------------------------

    def _compose_args(self) -> list[str]:
        return [
            self.docker_binary,
            "compose",
            "-p",
            self.project_name,
            "-f",
            self.compose_file,
        ]

    async def _require_compose(self) -> None:
        if shutil.which(self.docker_binary) is None:
            raise InfrastructureProviderUnavailable(
                f"docker binary not on PATH: {self.docker_binary!r}",
                provider=self.provider_alias,
            )
        if not os.path.exists(self.compose_file):
            raise InfrastructureProviderUnavailable(
                f"compose file not found: {self.compose_file!r}",
                provider=self.provider_alias,
            )

    async def _run(
        self,
        args: list[str],
        *,
        timeout: float | None = 120,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise InfrastructureProviderError(
                f"docker compose command timed out after {timeout}s",
                code="timeout",
                provider=self.provider_alias,
            )
        return (
            proc.returncode or 0,
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iter_json_lines(payload: str):
    """``docker compose ps --format json`` emits one JSON doc per line."""
    payload = payload.strip()
    if not payload:
        return
    # Newer compose versions emit a JSON array; older emit JSONL.
    if payload.startswith("["):
        try:
            for entry in json.loads(payload):
                yield entry
            return
        except json.JSONDecodeError:
            pass
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _parse_ps_output(
    payload: str, *, service_id: str, provider_alias: str
) -> DeploymentStatus:
    entries = list(_iter_json_lines(payload))
    if not entries:
        return DeploymentStatus(
            service_id=service_id,
            provider=provider_alias,
            phase=DeploymentLifecyclePhase.STOPPED,
            replicas_desired=0,
            replicas_ready=0,
        )

    replicas_total = len(entries)
    running = sum(
        1
        for e in entries
        if str(e.get("State", "")).lower() == "running"
        or str(e.get("state", "")).lower() == "running"
    )

    if running == replicas_total:
        phase = DeploymentLifecyclePhase.RUNNING
    elif running > 0:
        phase = DeploymentLifecyclePhase.DEGRADED
    else:
        phase = DeploymentLifecyclePhase.STOPPED

    image = (
        entries[0].get("Image")
        or entries[0].get("image")
        or None
    )

    return DeploymentStatus(
        service_id=service_id,
        provider=provider_alias,
        phase=phase,
        replicas_desired=replicas_total,
        replicas_ready=running,
        image=image,
        namespace=None,
        last_transition_at=_now(),
        conditions=entries,
    )


def _looks_like_secret(key: str) -> bool:
    """Crude redaction filter for env keys returned by ``docker compose config``."""
    upper = key.upper()
    return any(
        marker in upper
        for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY", "CREDENTIAL", "PRIVATE")
    )


def _parse_docker_stats(stats: dict) -> tuple[float, float, float]:
    """Translate the docker daemon's stats payload to (cpu%, mem%, mem_bytes)."""
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cpu_delta = float(cpu_stats.get("cpu_usage", {}).get("total_usage", 0)) - float(
            precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = float(cpu_stats.get("system_cpu_usage", 0)) - float(
            precpu_stats.get("system_cpu_usage", 0)
        )
        online_cpus = float(cpu_stats.get("online_cpus", 1))
        cpu_pct = (cpu_delta / system_delta) * online_cpus * 100.0 if system_delta > 0 else 0.0

        mem_stats = stats.get("memory_stats", {})
        mem_used = float(mem_stats.get("usage", 0))
        mem_limit = float(mem_stats.get("limit", 1)) or 1.0
        mem_pct = (mem_used / mem_limit) * 100.0
        return cpu_pct, mem_pct, mem_used
    except Exception:  # noqa: BLE001
        return 0.0, 0.0, 0.0


__all__ = ["DockerComposeProvider"]
