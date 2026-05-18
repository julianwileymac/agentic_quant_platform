"""GCP Secret Manager :class:`SecretStore`.

Resolves credentials from a GCP project's Secret Manager via the
``google-cloud-secret-manager`` SDK + Application Default Credentials
(operator laptop: gcloud user; CI: service-account file; GKE:
Workload Identity).

Key naming convention: ``{AQP_GCP_SECRET_PREFIX}<service>-<purpose>``
(GCP disallows ``/`` and ``.`` in secret IDs so we use hyphens). The
store always reads the ``latest`` version.

Optional dep: missing ``google-cloud-secret-manager`` -> the store
returns ``None`` for every key, letting the resolver fall through.
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
from aqp.credentials.stores.azure_keyvault_store import PRIORITY_AZURE_KV

logger = logging.getLogger(__name__)


PRIORITY_GCP_SM = PRIORITY_AZURE_KV  # 30 — same tier as AWS / Azure


def _normalize_id(prefix: str, key: CredentialKey) -> str:
    """Collapse a CredentialKey to a GCP-safe secret id.

    GCP secret IDs must match ``[a-zA-Z][a-zA-Z0-9_-]{0,254}``. We
    apply the ``AQP_GCP_SECRET_PREFIX`` (defaults to ``aqp-``) then
    sanitize the service / purpose pair.
    """
    raw = f"{prefix}{key.service}-{key.purpose}"
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:255] or "aqp"


class GcpSecretManagerStore(SecretStore):
    """GCP Secret Manager-backed :class:`SecretStore`."""

    store_kind = "gcp_secretmanager"
    store_alias = "GcpSecretManagerStore"
    store_priority = PRIORITY_GCP_SM

    def __init__(
        self,
        project_id: str | None = None,
        prefix: str | None = None,
    ) -> None:
        self._project_id_override = (project_id or "").strip() or None
        self._prefix_override = (prefix or "").strip() or None
        self._client: Any | None = None
        self._available: bool | None = None

    def _project_id(self) -> str:
        if self._project_id_override:
            return self._project_id_override
        try:
            from aqp.config import settings

            return str(getattr(settings, "gcp_project_id", "") or "").strip()
        except Exception:
            return ""

    def _prefix(self) -> str:
        if self._prefix_override:
            return self._prefix_override
        try:
            from aqp.config import settings

            return str(getattr(settings, "gcp_secret_prefix", "aqp-") or "aqp-")
        except Exception:
            return "aqp-"

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._available is False:
            return None
        try:
            from google.cloud import secretmanager  # type: ignore
        except ImportError:
            logger.info(
                "GcpSecretManagerStore disabled: google-cloud-secret-manager not "
                "installed (pip install agentic-quant-platform[cloud-gcp])"
            )
            self._available = False
            return None
        if not self._project_id():
            logger.debug("GcpSecretManagerStore: AQP_GCP_PROJECT_ID empty; disabled")
            self._available = False
            return None
        try:
            self._client = secretmanager.SecretManagerServiceClient()
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("GcpSecretManagerStore client init failed: %s", exc)
            self._available = False
            return None
        return self._client

    def get(self, key: CredentialKey) -> Credential | None:
        client = self._get_client()
        if client is None:
            return None
        secret_id = _normalize_id(self._prefix(), key)
        resource = f"projects/{self._project_id()}/secrets/{secret_id}/versions/latest"
        try:
            resp = client.access_secret_version(name=resource)
        except Exception as exc:  # noqa: BLE001 - missing secret -> normal miss
            logger.debug(
                "GcpSecretManagerStore miss for %s (resource=%s): %s",
                key,
                resource,
                exc,
            )
            return None
        try:
            raw = resp.payload.data.decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        fields = _parse_payload(raw)
        if not fields:
            return None
        return Credential(fields=fields, source=self.store_kind)


def _parse_payload(raw: str) -> dict[str, str]:
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


__all__ = ["GcpSecretManagerStore", "PRIORITY_GCP_SM"]
