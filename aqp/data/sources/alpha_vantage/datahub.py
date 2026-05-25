"""Best-effort DataHub metadata emission for Alpha Vantage datasets."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from aqp.config import settings
from aqp.credentials import get_datahub_credential

logger = logging.getLogger(__name__)


def dataset_urn(platform: str, name: str, env: str | None = None) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env or settings.datahub_env or 'PROD'})"


def emit_dataset_properties(
    *,
    platform: str,
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
) -> bool:
    """Emit dataset properties directly to DataHub when configured."""

    cred = get_datahub_credential()
    gms_url = (cred.get("gms_url") or settings.datahub_gms_url or "").rstrip("/")
    if not gms_url:
        return False

    urn = dataset_urn(platform, name)
    payload = {
        "entity": {
            "value": {
                "com.linkedin.metadata.snapshot.DatasetSnapshot": {
                    "urn": urn,
                    "aspects": [
                        {
                            "com.linkedin.dataset.DatasetProperties": {
                                "description": description,
                                "customProperties": {
                                    key: str(value)
                                    for key, value in (properties or {}).items()
                                    if value is not None
                                },
                            }
                        }
                    ],
                }
            }
        }
    }
    # AGENTS Rule 26 — token from CredentialResolver, not settings.
    headers = {"Content-Type": "application/json"}
    token = cred.get("token", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            response = client.post(f"{gms_url}/entities?action=ingest", json=payload)
            response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("DataHub dataset property emit failed for %s: %s", urn, exc)
        return False


__all__ = ["dataset_urn", "emit_dataset_properties"]
