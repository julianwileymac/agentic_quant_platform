"""Filesystem-backed :class:`SecretStore`.

Reads JSON payloads written by bootstrap workflows under
``settings.bootstrap_state_dir``. The reference example is
:func:`aqp.services.iceberg_bootstrap.persist_principal_credentials`,
which writes ``polaris-principal.json`` after Polaris mints the
``aqp_runtime`` principal.

Layout of ``bootstrap_state_dir``::

    bootstrap_state_dir/
        polaris-principal.json   # {"client_id": ..., "client_secret": ..., "principal": ...}
        <future bootstraps>.json

The store is read-only and silent on missing files (returns ``None`` so
the resolver continues to env). Bootstrap modules write through their
own helpers; this store exists only to expose those payloads to the
resolver chain.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aqp.credentials.protocol import (
    PRIORITY_FILE,
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)

# Map (service, purpose) -> filename inside bootstrap_state_dir.
# Adding a new file-backed credential = one entry here + one bootstrap
# writer that writes the file.
_FILE_MAP: dict[tuple[str, str], str] = {
    ("polaris", "oauth"): "polaris-principal.json",
    ("polaris", "rest"): "polaris-principal.json",
    ("iceberg", "rest"): "polaris-principal.json",
}


class FileSecretStore(SecretStore):
    """Loads bootstrap-persisted credentials from disk."""

    store_kind = "file"
    store_alias = "FileSecretStore"
    store_priority = PRIORITY_FILE

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._base_dir_override = Path(base_dir).expanduser() if base_dir else None

    def _base_dir(self) -> Path:
        if self._base_dir_override is not None:
            return self._base_dir_override
        try:
            from aqp.config import settings

            return Path(settings.bootstrap_state_dir).expanduser()
        except Exception:  # pragma: no cover - settings always available in prod
            return Path("./data/bootstrap").expanduser()

    def _read(self, name: str) -> dict[str, Any] | None:
        path = self._base_dir() / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("FileSecretStore: failed to read %s: %s", path, exc)
            return None

    def get(self, key: CredentialKey) -> Credential | None:
        filename = _FILE_MAP.get((key.service, key.purpose))
        if filename is None:
            return None
        payload = self._read(filename)
        if not isinstance(payload, dict):
            return None

        client_id = str(payload.get("client_id") or payload.get("clientId") or "")
        client_secret = str(
            payload.get("client_secret")
            or payload.get("clientSecret")
            or payload.get("secret")
            or ""
        )
        if not client_id or not client_secret:
            return None

        if key.purpose == "oauth":
            return Credential(
                fields={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "principal": str(payload.get("principal") or ""),
                },
                source=self.store_kind,
            )
        if key.purpose == "rest":
            return Credential(
                fields={"credential": f"{client_id}:{client_secret}"},
                source=self.store_kind,
            )
        return None


__all__ = ["FileSecretStore"]
