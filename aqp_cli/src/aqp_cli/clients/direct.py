"""Direct local probes (Docker socket, kubernetes context, filesystem)
and the emergency direct-OIDC fallback.

Used only when the control plane is unreachable, or with an explicit
``--direct`` flag that requires ``--i-understand`` per AQP rule 27.
"""
from __future__ import annotations

from typing import Any


class DirectProbe:
    """Best-effort local discovery of AQP services."""

    def discover(self) -> list[dict[str, Any]]:
        """Return [{name, cluster, namespace, state}, ...]. Stub returns []."""
        return []


class DirectAuth:
    """Direct OIDC fallback (Auth0 / generic OIDC discovery, then device code)."""

    def device_code_login(self) -> str | None:
        """Drive a device-code flow against the configured IdP. Stub."""
        return None
