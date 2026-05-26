"""HashiCorp ``vault-secrets-operator`` projected secret store.

Phase 4 §7.6 (RESTRUCTURING_PLAN.md). The
``vault-secrets-operator`` (VSO) Helm chart watches Vault KV v2 paths
and projects them as standard Kubernetes :class:`Secret` objects via
the ``VaultStaticSecret`` CRD:

.. code-block:: yaml

    apiVersion: secrets.hashicorp.com/v1beta1
    kind: VaultStaticSecret
    metadata:
      name: aqp-cell-postgres-credentials
      namespace: cell-shared-std-us-east-1a
    spec:
      mount: cells/shared-std/postgres
      path: cell-shared-std-us-east-1a
      destination:
        create: true
        name: postgres-credentials
      refreshAfter: 30m
      rolloutRestartTargets:
        - kind: Deployment
          name: aqp-cell-api

The pod mounts the projected :class:`Secret` via standard
``envFrom: secretRef:`` or ``volumes: secret:`` references. From AQP's
point of view, the workflow is the same as the existing
:class:`FileSecretStore` — read a directory of static files written by
the orchestrator — but the orchestrator's contract is "ALWAYS fresh,
within the Vault Transit refresh window" rather than "whatever was
hand-pasted at boot time".

The envelope key for ``vault_transit.encrypt`` stays in Vault Transit
(unchanged from :mod:`aqp.credentials.vault_transit`). Only the
operational secrets at rest in Kubernetes flow through this store.

Priority is :data:`PRIORITY_VAULT_STATIC` (15) — higher than the
on-demand AppRole Vault store (20) because:

1. The projected secret is already cached on disk, no Vault round trip.
2. Operators who wire VSO want it to win over manual file writes
   (which sit at PRIORITY_FILE = 50).

The store degrades cleanly when the mount path is empty / unset.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from aqp.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


# M2M (10) > VaultStaticSecret (15) > Vault AppRole (20) > Cloud SM (30) > File (50) > Env (100).
PRIORITY_VAULT_STATIC = 15


_DEFAULT_MOUNT_DIR = "/var/run/secrets/vault-secrets-operator"


class VaultStaticSecretStore(SecretStore):
    """:class:`SecretStore` backed by ``vault-secrets-operator`` projections.

    Each Vault KV v2 path becomes a Kubernetes Secret. Operators wire
    the Secret onto the pod via:

    - ``envFrom: secretRef: { name: <secret-name> }`` — every key in
      the Secret lands as an env var. This store reads via :func:`os.environ`
      transparently (the existing :class:`EnvSecretStore` already
      handles this case at lower priority).
    - ``volumes: secret: { secretName: <secret-name> }`` mounted under
      ``/var/run/secrets/vault-secrets-operator/<key.purpose>/``.

    This store handles the second pattern — reads files under a
    per-(service, purpose) directory matching the
    ``CredentialKey(service, purpose)`` tuple, so the projection layout
    cleanly maps to the AQP credential key namespace.

    The mount root is configurable via
    ``AQP_VAULT_STATIC_MOUNT_DIR``; default is the conventional
    ``/var/run/secrets/vault-secrets-operator``.
    """

    store_kind = "vault_static_secret"
    store_alias = "VaultStaticSecretStore"
    store_priority = PRIORITY_VAULT_STATIC

    def __init__(
        self,
        mount_dir: str | None = None,
        *,
        cache_ttl_seconds: float = 5.0,
    ) -> None:
        self._mount_dir_override = (mount_dir or "").strip() or None
        self._cache_ttl = max(0.0, cache_ttl_seconds)
        self._lock = threading.RLock()
        # tuple[service, purpose] -> (read_at, Credential | None)
        self._cache: dict[tuple[str, str], tuple[float, Credential | None]] = {}

    # ------------------------------------------------------------------
    # SecretStore
    # ------------------------------------------------------------------

    def get(self, key: CredentialKey) -> Credential | None:
        mount = self._mount_dir()
        if not mount:
            return None
        cache_key = (key.service, key.purpose)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < self._cache_ttl:
                return cached[1]

        directory = Path(mount) / f"{key.service}.{key.purpose}"
        if not directory.exists():
            # Also try the slash-separated layout some operators prefer.
            alt = Path(mount) / key.service / key.purpose
            if alt.exists():
                directory = alt
            else:
                with self._lock:
                    self._cache[cache_key] = (time.monotonic(), None)
                return None

        try:
            fields = self._read_directory(directory)
        except OSError as exc:
            logger.warning(
                "vault_static_secret: read failed for %s.%s: %s",
                key.service,
                key.purpose,
                exc,
            )
            with self._lock:
                self._cache[cache_key] = (time.monotonic(), None)
            return None

        if not fields:
            with self._lock:
                self._cache[cache_key] = (time.monotonic(), None)
            return None

        credential = Credential(
            fields=fields,
            source=f"{self.store_kind}:{directory}",
            # refreshAfter on the VaultStaticSecret CR is the only TTL
            # signal; we report `None` and let the resolver re-call us
            # on the configured cache_ttl_seconds.
            ttl_seconds=None,
        )
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), credential)
        return credential

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _mount_dir(self) -> str:
        if self._mount_dir_override is not None:
            return self._mount_dir_override
        return os.environ.get("AQP_VAULT_STATIC_MOUNT_DIR", _DEFAULT_MOUNT_DIR)

    def _read_directory(self, directory: Path) -> dict[str, str]:
        """Read every file in *directory* into a dict, stripping trailing whitespace.

        Files starting with ``..`` are Kubernetes projected-secret
        atomic-write markers — skip them.
        """
        out: dict[str, str] = {}
        for entry in directory.iterdir():
            if entry.name.startswith(".."):
                continue
            if entry.name.startswith("."):
                continue
            if not entry.is_file():
                continue
            try:
                raw = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary projection (rare; X.509 keys come through other paths).
                raw = entry.read_bytes().decode("utf-8", errors="replace")
            out[entry.name] = raw.rstrip("\r\n")
        return out

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "mount_dir": self._mount_dir(),
                "cache_ttl_seconds": self._cache_ttl,
                "cached_keys": [
                    f"{svc}.{purpose}" for (svc, purpose) in sorted(self._cache)
                ],
            }
        )
        return out


__all__ = ["PRIORITY_VAULT_STATIC", "VaultStaticSecretStore"]
