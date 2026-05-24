"""Client for the per-pod secret-broker sidecar."""
from __future__ import annotations

import json
import socket
from typing import Any


_DEFAULT_SOCKET_PATH = "/var/run/aqp-secret-broker.sock"


class SecretBrokerClient:
    """Synchronous Unix-domain-socket client."""

    def __init__(self, *, socket_path: str = _DEFAULT_SOCKET_PATH) -> None:
        self._socket_path = socket_path

    def resolve(
        self,
        *,
        service: str,
        label: str = "primary",
        field: str = "api_key",
        timeout_s: float = 2.0,
    ) -> str | None:
        req = {"service": service, "label": label, "field": field}
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout_s)
            sock.connect(self._socket_path)
            sock.send(json.dumps(req).encode("utf-8"))
            raw = sock.recv(16_384)
            sock.close()
        except Exception:  # noqa: BLE001
            return None
        try:
            payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not payload.get("ok"):
            return None
        return str(payload.get("value") or "") or None


__all__ = ["SecretBrokerClient"]
