"""Settings-backed :class:`SecretStore` — the always-available safety net.

Reads from the canonical :class:`aqp.config.Settings` instance via
``from aqp.config import settings``. This is the lowest-priority store
in the resolver chain; values here are the static seeds defined in
``.env.example`` / ``docker-compose*.yml``.

Adding a new service to the resolver = add a branch in :meth:`get` that
maps the :class:`CredentialKey` to a small dict of settings fields.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.credentials.protocol import (
    PRIORITY_ENV,
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


class EnvSecretStore(SecretStore):
    """Resolves credentials from :mod:`aqp.config.settings`.

    Always returns a :class:`Credential` for known keys (even if the
    underlying setting is empty); higher-priority stores override.
    Returning ``None`` here would defeat the safety-net role.
    """

    store_kind = "env"
    store_alias = "EnvSecretStore"
    store_priority = PRIORITY_ENV

    def __init__(self, settings_obj: Any | None = None) -> None:
        self._settings = settings_obj

    def _settings_handle(self) -> Any:
        if self._settings is not None:
            return self._settings
        from aqp.config import settings  # local import; avoids module-import cycles

        return settings

    def get(self, key: CredentialKey) -> Credential | None:
        s = self._settings_handle()
        service = key.service
        purpose = key.purpose

        if service == "polaris" and purpose == "oauth":
            return Credential(
                fields={
                    "client_id": str(s.polaris_client_id or ""),
                    "client_secret": str(s.polaris_client_secret or ""),
                    "principal": str(getattr(s, "iceberg_principal_name", "") or ""),
                },
                source=self.store_kind,
            )
        if service == "polaris" and purpose == "rest":
            client_id = str(s.polaris_client_id or "")
            client_secret = str(s.polaris_client_secret or "")
            value = (
                str(s.iceberg_rest_credential or "").strip()
                or (f"{client_id}:{client_secret}" if client_id and client_secret else "")
            )
            return Credential(
                fields={"credential": value} if value else {},
                source=self.store_kind,
            )
        if service == "iceberg" and purpose == "rest":
            return Credential(
                fields={
                    "credential": str(s.iceberg_rest_credential or ""),
                    "token": str(s.iceberg_rest_token or ""),
                    "oauth2_server_uri": str(s.iceberg_rest_oauth2_server_uri or ""),
                    "scope": str(s.iceberg_rest_scope or ""),
                },
                source=self.store_kind,
            )
        if service == "trino" and purpose == "basic":
            return Credential(
                fields={
                    "user": str(getattr(s, "trino_admin_user", "") or ""),
                    "source": str(getattr(s, "trino_admin_source", "") or ""),
                },
                source=self.store_kind,
            )
        if service == "minio" and purpose == "static":
            return Credential(
                fields={
                    "access_key": str(getattr(s, "s3_access_key", "") or ""),
                    "secret_key": str(getattr(s, "s3_secret_key", "") or ""),
                    "endpoint_url": str(getattr(s, "s3_endpoint_url", "") or ""),
                    "region": str(getattr(s, "s3_region", "") or ""),
                },
                source=self.store_kind,
            )
        if service == "neo4j" and purpose == "basic":
            return Credential(
                fields={
                    "user": str(getattr(s, "neo4j_user", "") or ""),
                    "password": str(getattr(s, "neo4j_password", "") or ""),
                    "uri": str(getattr(s, "neo4j_uri", "") or ""),
                },
                source=self.store_kind,
            )
        return None


__all__ = ["EnvSecretStore"]
