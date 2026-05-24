"""CLI authentication primitives.

Two top-level surfaces:

- :mod:`aqp_cli.auth.device_flow` — RFC 8628 Device Authorization Grant.
  The headless / headed terminal flow used when the operator has a
  browser available on the same machine OR on a separate device.
- :mod:`aqp_cli.auth.keyring_store` — OS-native credential persistence
  (macOS Keychain, Windows Credential Locker, Linux Secret Service)
  with a ``keyrings.alt`` encrypted-file fallback for headless servers.

Both modules are imported on demand so the CLI's core surface
(``aqp-cli services list``, ``aqp-cli auth whoami``) keeps starting
even when the optional ``keyring`` extra isn't installed.
"""
from __future__ import annotations

__all__ = ["device_flow", "keyring_store"]
