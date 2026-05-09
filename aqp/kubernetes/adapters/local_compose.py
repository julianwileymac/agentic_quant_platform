"""Local ``docker compose`` adapter.

Backs the new ``docker-compose.platform.yml`` overlay (Milestone 5):
the AQP "cluster" is the local Docker daemon, and operations like
``scale_deployment`` and ``pod_logs`` shell out to ``docker compose``
commands.

This adapter is lightweight by design — operations are safe-by-default
and never raise on missing services (returns the stderr instead). For
real cluster ops, use :class:`InClusterAdapter` or
:class:`RpiClusterAdapter`.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from aqp.kubernetes.protocol import (
    KubernetesAdapter,
    KubernetesAdapterError,
)

logger = logging.getLogger(__name__)


class LocalComposeAdapter(KubernetesAdapter):
    """Treat ``docker compose`` services as the cluster surface."""

    adapter_kind = "local_compose"
    adapter_alias = "LocalComposeAdapter"

    def __init__(
        self,
        *,
        compose_files: list[Path] | None = None,
        project_directory: Path | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._compose_files = list(compose_files or [])
        self._cwd = project_directory
        self._timeout = max(5, int(timeout_seconds))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(shutil.which("docker"))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compose_args(self) -> list[str]:
        args: list[str] = ["docker", "compose"]
        for f in self._compose_files:
            args.extend(["-f", str(f)])
        return args

    def _run(self, *cmd: str) -> tuple[int, str, str]:
        if not self.is_available():
            raise KubernetesAdapterError("docker is not on PATH")
        try:
            result = subprocess.run(
                list(cmd),
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise KubernetesAdapterError(
                f"docker command timed out after {self._timeout}s: {' '.join(cmd)}"
            ) from exc
        return result.returncode, result.stdout, result.stderr

    # ------------------------------------------------------------------
    # Ops
    # ------------------------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        # docker compose treats compose service names as deployments;
        # ``namespace`` is unused but kept for parity with the cluster
        # adapters.
        del namespace
        rc, stdout, stderr = self._run(
            *self._compose_args(),
            "up",
            "-d",
            "--scale",
            f"{name}={int(replicas)}",
            name,
        )
        if rc != 0:
            raise KubernetesAdapterError(f"compose scale failed: {stderr or stdout}")
        return {"service": name, "replicas": int(replicas), "stdout": stdout.strip()}

    def pod_logs(
        self, *, namespace: str, name: str, tail_lines: int = 200
    ) -> str:
        del namespace
        rc, stdout, stderr = self._run(
            *self._compose_args(),
            "logs",
            "--no-color",
            "--tail",
            str(int(tail_lines)),
            name,
        )
        if rc != 0:
            raise KubernetesAdapterError(f"compose logs failed: {stderr or stdout}")
        return stdout


__all__ = ["LocalComposeAdapter"]
