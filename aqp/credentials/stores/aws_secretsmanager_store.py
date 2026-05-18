"""AWS Secrets Manager :class:`SecretStore`.

Resolves credentials from AWS Secrets Manager via ``boto3``. Reads
the credential payload from a secret whose name is
``{AQP_AWS_SECRETSMANAGER_PREFIX}<service>/<purpose>`` (Secrets
Manager allows ``/`` in names so we keep the natural shape).

Secret values may be:

- JSON object — every key becomes a :class:`Credential.fields` entry.
- Plain string — stored under the ``value`` key.

Auth follows the standard boto3 credential chain (IRSA when running
in an EKS pod, env vars otherwise). The store is OPTIONAL: missing
``boto3`` -> ``return None``, no resolver impact.
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


PRIORITY_AWS_SM = PRIORITY_AZURE_KV  # same tier (30); only one cloud active at a time


class AwsSecretsManagerStore(SecretStore):
    """AWS Secrets Manager-backed :class:`SecretStore`."""

    store_kind = "aws_secretsmanager"
    store_alias = "AwsSecretsManagerStore"
    store_priority = PRIORITY_AWS_SM

    def __init__(
        self,
        region: str | None = None,
        prefix: str | None = None,
    ) -> None:
        self._region_override = (region or "").strip() or None
        self._prefix_override = (prefix or "").strip() or None
        self._client: Any | None = None
        self._available: bool | None = None

    # ------------------------------------------------------------------
    # Config + lazy client
    # ------------------------------------------------------------------

    def _region(self) -> str:
        if self._region_override:
            return self._region_override
        try:
            from aqp.config import settings

            return str(getattr(settings, "aws_region", "") or "").strip()
        except Exception:
            return ""

    def _prefix(self) -> str:
        if self._prefix_override:
            return self._prefix_override
        try:
            from aqp.config import settings

            return str(getattr(settings, "aws_secretsmanager_prefix", "aqp/") or "aqp/")
        except Exception:
            return "aqp/"

    def _secret_name(self, key: CredentialKey) -> str:
        prefix = self._prefix()
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return f"{prefix}{key.service}/{key.purpose}"

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._available is False:
            return None
        try:
            import boto3  # type: ignore
        except ImportError:
            logger.info(
                "AwsSecretsManagerStore disabled: boto3 not installed (pip install "
                "agentic-quant-platform[cloud-aws])"
            )
            self._available = False
            return None
        try:
            region = self._region() or None
            self._client = boto3.client("secretsmanager", region_name=region)
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("AwsSecretsManagerStore client init failed: %s", exc)
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
        name = self._secret_name(key)
        try:
            resp = client.get_secret_value(SecretId=name)
        except Exception as exc:  # noqa: BLE001 - missing secret -> normal miss
            logger.debug(
                "AwsSecretsManagerStore miss for %s (name=%s): %s",
                key,
                name,
                exc,
            )
            return None
        raw = resp.get("SecretString") or ""
        if not raw and "SecretBinary" in resp:
            try:
                raw = resp["SecretBinary"].decode("utf-8", errors="replace")
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


__all__ = ["AwsSecretsManagerStore", "PRIORITY_AWS_SM"]
