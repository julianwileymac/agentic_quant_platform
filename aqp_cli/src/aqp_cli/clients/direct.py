"""Direct local probes and emergency direct-auth fallback."""

from __future__ import annotations

import os
import socket
from typing import Any


class DirectProbe:
    """Best-effort local discovery of AQP services."""

    _PORT_MAP: dict[int, str] = {
        3000: "theia-ide",
        3001: "aqp-client",
        8000: "aqp-api",
        8050: "dash",
        8800: "aqp-admin",
        8900: "aqp-admin-api",
        9000: "aqp-control-plane",
    }

    def _is_open(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def discover(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for port, name in sorted(self._PORT_MAP.items()):
            out.append(
                {
                    "name": name,
                    "cluster": "local",
                    "namespace": "-",
                    "state": "running" if self._is_open(port) else "down",
                    "port": str(port),
                }
            )
        return out


class DirectAuth:
    """Emergency direct auth mode.

    AQP prefers brokered auth via the control plane, but this fallback allows
    users to provide a token directly in exceptional situations.
    """

    def device_code_login(self) -> str | None:
        return (
            os.environ.get("AQP_ACCESS_TOKEN") or os.environ.get("AQP_CP_TOKEN") or ""
        ).strip() or None
