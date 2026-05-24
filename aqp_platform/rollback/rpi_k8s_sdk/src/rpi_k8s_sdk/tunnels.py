"""kubectl port-forward helpers for private lab APIs."""

from __future__ import annotations

import contextlib
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Iterator

from .access import LocalAccessSettings, ServiceRef, load_settings


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass(slots=True)
class PortForwardTunnel:
    """Lifecycle wrapper around one `kubectl port-forward` process."""

    service: ServiceRef
    settings: LocalAccessSettings
    process: subprocess.Popen[str] | None = None

    @property
    def local_url(self) -> str:
        return self.service.local_url

    def command(self) -> list[str]:
        cmd = [
            "kubectl",
            "port-forward",
            f"svc/{self.service.name}",
            f"{self.service.local_port}:{self.service.port}",
            "-n",
            self.service.namespace,
        ]
        if self.settings.kube_context:
            cmd.extend(["--context", self.settings.kube_context])
        if self.settings.kubeconfig:
            cmd.extend(["--kubeconfig", self.settings.kubeconfig])
        return cmd

    def start(self, *, wait_seconds: float = 1.0) -> "PortForwardTunnel":
        if self.process and self.process.poll() is None:
            return self
        self.process = subprocess.Popen(
            self.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(wait_seconds)
        if self.process.poll() is not None:
            _, stderr = self.process.communicate(timeout=1)
            raise RuntimeError(f"port-forward failed for {self.service.name}: {stderr.strip()}")
        return self

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def __enter__(self) -> "PortForwardTunnel":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


class LocalTunnelManager:
    """Factory for the private tunnels used by local Python sessions."""

    def __init__(self, settings: LocalAccessSettings | None = None):
        self.settings = settings or load_settings()

    def tunnel(self, service: ServiceRef) -> PortForwardTunnel:
        return PortForwardTunnel(service=service, settings=self.settings)

    def datahub_gms(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.datahub_gms)

    def otel_collector(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.otel_collector)

    def argo_server(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.argo_server)

    def mlflow(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.mlflow)

    def minio(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.minio)

    def postgresql(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.postgresql)

    def redis(self) -> PortForwardTunnel:
        return self.tunnel(self.settings.redis)

    @contextlib.contextmanager
    def started(self, *services: ServiceRef) -> Iterator[list[PortForwardTunnel]]:
        tunnels = [self.tunnel(service).start() for service in services]
        try:
            yield tunnels
        finally:
            for tunnel in reversed(tunnels):
                tunnel.stop()

    @contextlib.contextmanager
    def bring_up_aqp_devloop(self) -> Iterator[list[PortForwardTunnel]]:
        """Open every tunnel an AQP local dev session typically needs.

        Tunnels: Postgres, Redis, MLflow, MinIO, OTel Collector, DataHub GMS,
        Argo Server.  Yields the started tunnels and tears them all down on
        exit.  Use as ``with LocalTunnelManager().bring_up_aqp_devloop():``.
        """

        services = [
            self.settings.postgresql,
            self.settings.redis,
            self.settings.mlflow,
            self.settings.minio,
            self.settings.otel_collector,
            self.settings.datahub_gms,
            self.settings.argo_server,
        ]
        with self.started(*services) as tunnels:
            yield tunnels
