"""HashiCorp Vault :class:`SecretStore` (KV v2 + AppRole).

Resolves credentials from a HashiCorp Vault cluster. Supports both:

- Token auth — the operator already has ``VAULT_TOKEN`` set or
  manually logged in (``vault login``); ``hvac`` picks it up.
- AppRole auth — :attr:`Settings.vault_role_id` and
  :attr:`Settings.vault_secret_id` are set; the store performs the
  AppRole login once and caches the token until expiry.

Secrets are read from KV v2 paths shaped
``{AQP_VAULT_MOUNT}/data/<service>/<purpose>``; the response's
``data.data`` field becomes the :class:`Credential.fields` dict
(every Vault secret is already a flat string-to-string mapping).

Priority is :data:`PRIORITY_VAULT` (20) — higher than the cloud
secret managers (30) because operators wiring Vault typically want
its policies to win over IRSA / Workload Identity defaults.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from aqp.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


PRIORITY_VAULT = 20  # M2M (10) > Vault (20) > Cloud SM (30) > File (50) > Env (100)


class HashicorpVaultSecretStore(SecretStore):
    """HashiCorp Vault-backed :class:`SecretStore`.

    The dependency on ``hvac`` is OPTIONAL. When ``hvac`` isn't
    installed or :attr:`Settings.vault_addr` is empty, the store
    returns ``None`` for every key.
    """

    store_kind = "hashicorp_vault"
    store_alias = "HashicorpVaultSecretStore"
    store_priority = PRIORITY_VAULT

    def __init__(
        self,
        addr: str | None = None,
        namespace: str | None = None,
        mount: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
    ) -> None:
        self._addr_override = (addr or "").strip() or None
        self._namespace_override = (namespace or "").strip() or None
        self._mount_override = (mount or "").strip() or None
        self._role_id_override = (role_id or "").strip() or None
        self._secret_id_override = (secret_id or "").strip() or None
        self._client: Any | None = None
        self._available: bool | None = None
        self._token_expiry: float = 0.0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Config + lazy client
    # ------------------------------------------------------------------

    def _settings(self) -> Any | None:
        try:
            from aqp.config import settings

            return settings
        except Exception:
            return None

    def _addr(self) -> str:
        if self._addr_override:
            return self._addr_override
        s = self._settings()
        return str(getattr(s, "vault_addr", "") or "").strip()

    def _namespace(self) -> str:
        if self._namespace_override:
            return self._namespace_override
        s = self._settings()
        return str(getattr(s, "vault_namespace", "") or "").strip()

    def _mount(self) -> str:
        if self._mount_override:
            return self._mount_override
        s = self._settings()
        return str(getattr(s, "vault_mount", "secret") or "secret")

    def _role_id(self) -> str:
        if self._role_id_override:
            return self._role_id_override
        s = self._settings()
        return str(getattr(s, "vault_role_id", "") or "").strip()

    def _secret_id(self) -> str:
        if self._secret_id_override:
            return self._secret_id_override
        s = self._settings()
        return str(getattr(s, "vault_secret_id", "") or "").strip()

    def _get_client(self) -> Any | None:
        with self._lock:
            if self._client is not None and time.time() < self._token_expiry:
                return self._client
            if self._available is False:
                return None
            try:
                import hvac  # type: ignore
            except ImportError:
                logger.info(
                    "HashicorpVaultSecretStore disabled: hvac not installed "
                    "(pip install agentic-quant-platform[vault])"
                )
                self._available = False
                return None
            addr = self._addr()
            if not addr:
                self._available = False
                return None
            try:
                kwargs: dict[str, Any] = {"url": addr}
                ns = self._namespace()
                if ns:
                    kwargs["namespace"] = ns
                client = hvac.Client(**kwargs)
                # AppRole login when role_id + secret_id provided;
                # otherwise rely on VAULT_TOKEN env (hvac default).
                role_id = self._role_id()
                secret_id = self._secret_id()
                if role_id and secret_id:
                    resp = client.auth.approle.login(
                        role_id=role_id, secret_id=secret_id
                    )
                    lease = int(resp.get("auth", {}).get("lease_duration") or 3600)
                    self._token_expiry = time.time() + max(60, lease - 30)
                else:
                    # Token auth — assume token is long-lived (hvac
                    # already populated client.token from VAULT_TOKEN).
                    self._token_expiry = time.time() + 3600
                if not client.is_authenticated():
                    logger.warning(
                        "HashicorpVaultSecretStore: client.is_authenticated() returned False"
                    )
                    self._available = False
                    return None
                self._client = client
                self._available = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("HashicorpVaultSecretStore client init failed: %s", exc)
                self._available = False
                return None
            return self._client

    # ------------------------------------------------------------------
    # Lookup (KV v2)
    # ------------------------------------------------------------------

    def get(self, key: CredentialKey) -> Credential | None:
        client = self._get_client()
        if client is None:
            return None
        path = f"{key.service}/{key.purpose}"
        mount = self._mount()
        try:
            resp = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=mount,
            )
        except Exception as exc:  # noqa: BLE001 - normal miss path
            logger.debug(
                "HashicorpVaultSecretStore miss for %s (mount=%s path=%s): %s",
                key,
                mount,
                path,
                exc,
            )
            return None
        try:
            data = (resp or {}).get("data", {}).get("data", {}) or {}
        except Exception:
            data = {}
        if not isinstance(data, dict) or not data:
            return None
        fields = {str(k): str(v) for k, v in data.items() if v is not None}
        if not fields:
            return None
        ttl = None
        try:
            metadata = (resp or {}).get("data", {}).get("metadata", {})
            lease = metadata.get("lease_duration") if isinstance(metadata, dict) else None
            if isinstance(lease, int) and lease > 0:
                ttl = lease
        except Exception:
            ttl = None
        return Credential(
            fields=fields,
            source=self.store_kind,
            ttl_seconds=ttl,
        )


__all__ = ["HashicorpVaultSecretStore", "PRIORITY_VAULT"]
