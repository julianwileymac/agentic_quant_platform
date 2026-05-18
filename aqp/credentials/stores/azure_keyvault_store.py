"""Azure Key Vault :class:`SecretStore`.

Resolves credentials from an Azure Key Vault instance using the
``azure-keyvault-secrets`` SDK + :class:`DefaultAzureCredential` (so
the operator laptop's ``az login`` cache, a CI service-principal env,
and in-AKS Workload Identity all light up the same code path).

Key naming convention: ``aqp-<service>-<purpose>`` (Azure Key Vault
disallows ``:``, ``/``, ``.`` in secret names so we collapse the
:class:`CredentialKey` pair to a single hyphenated string). Multi-
field secrets are stored as JSON in the secret value; the store
parses them back into the :class:`Credential.fields` dict.

This store is OPTIONAL: when ``azure-keyvault-secrets`` or
``azure-identity`` is not installed, :meth:`get` returns ``None`` so
the resolver chain falls through to the file / env stores.

Priority is :data:`PRIORITY_AZURE_KV` (30) — between the M2M issuer
(10) and the file store (50). Cloud-deployed services typically read
from the matching cloud's secret store first, falling back to env
when the SDK is unreachable.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from aqp.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


# Cloud secret stores sit between PRIORITY_M2M (10) and PRIORITY_FILE
# (50). Define here so the resolver-priority comments stay consistent.
PRIORITY_AZURE_KV = 30


def _normalize_key(key: CredentialKey) -> str:
    """Collapse a (service, purpose) pair to an Azure-safe secret name.

    Key Vault secret names must match ``^[0-9a-zA-Z-]{1,127}$``. We
    normalize underscores / colons / dots to hyphens and lowercase
    everything so the same logical key always maps to the same vault
    entry.
    """
    raw = f"aqp-{key.service}-{key.purpose}".lower()
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in raw)
    # Collapse runs of dashes + trim.
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:127] or "aqp"


class AzureKeyVaultSecretStore(SecretStore):
    """Azure Key Vault secret store (Workload Identity friendly)."""

    store_kind = "azure_keyvault"
    store_alias = "AzureKeyVaultSecretStore"
    store_priority = PRIORITY_AZURE_KV

    def __init__(self, vault_url: str | None = None) -> None:
        self._vault_url_override = (vault_url or "").strip() or None
        self._client: Any | None = None
        self._available: bool | None = None

    # ------------------------------------------------------------------
    # Lazy client + capability gating
    # ------------------------------------------------------------------

    def _vault_url(self) -> str:
        if self._vault_url_override:
            return self._vault_url_override
        try:
            from aqp.config import settings

            return str(getattr(settings, "azure_keyvault_url", "") or "").strip()
        except Exception:  # pragma: no cover - settings always present in prod
            return ""

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._available is False:
            return None
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore
            from azure.keyvault.secrets import SecretClient  # type: ignore
        except ImportError:
            logger.info(
                "AzureKeyVaultSecretStore disabled: azure-keyvault-secrets / "
                "azure-identity not installed (pip install "
                "agentic-quant-platform[cloud-azure])"
            )
            self._available = False
            return None
        url = self._vault_url()
        if not url:
            logger.debug("AzureKeyVaultSecretStore: AQP_AZURE_KEYVAULT_URL is empty; disabled")
            self._available = False
            return None
        try:
            credential = DefaultAzureCredential()
            self._client = SecretClient(vault_url=url, credential=credential)
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("AzureKeyVaultSecretStore client init failed: %s", exc)
            self._available = False
            return None
        return self._client

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, key: CredentialKey) -> Credential | None:
        client = self._get_client()
        if client is None:
            return None
        name = _normalize_key(key)
        try:
            secret = client.get_secret(name)
        except Exception as exc:  # noqa: BLE001 - missing secret is a normal miss
            logger.debug(
                "AzureKeyVaultSecretStore miss for %s (name=%s): %s",
                key,
                name,
                exc,
            )
            return None
        value = (secret.value if secret else None) or ""
        fields = _parse_payload(value)
        if not fields:
            return None
        return Credential(fields=fields, source=self.store_kind)


def _parse_payload(raw: str) -> dict[str, str]:
    """Parse a Key Vault secret value into a :class:`Credential.fields` dict.

    Two formats supported:

    - JSON object — ``{"client_id": "...", "client_secret": "..."}``;
      every value is coerced to a string.
    - Plain string — stored under the ``value`` key. Callers asking
      for a single-field credential (e.g. an API token) read
      ``credential.get("value")``.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except Exception:
            return {"value": raw}
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if v is not None}
    return {"value": raw}


__all__ = ["AzureKeyVaultSecretStore", "PRIORITY_AZURE_KV"]
