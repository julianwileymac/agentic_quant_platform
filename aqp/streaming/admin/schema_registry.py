"""Apicurio schema registry HTTP client.

Apicurio exposes both its own v2 API and a Confluent-compatible
``/apis/ccompat/v7`` shim. We prefer ccompat for read-paths because
the wire shape matches every other AQP integration (ksql, librdkafka
schema-registry helpers, etc.). Writes go through the v2 API which
exposes content-id semantics that match the canonical schema bundle.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from aqp.config import settings

logger = logging.getLogger(__name__)


class SchemaRegistryError(RuntimeError):
    """Raised when the schema registry returns a non-2xx response."""


class ApicurioSchemaRegistry:
    """Tiny HTTP wrapper used by the ``/streaming/kafka/schema-registry`` API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_s: float = 10.0,
        token: str | None = None,
    ) -> None:
        url = (
            base_url
            or getattr(settings, "kafka_admin_schema_registry_url", "")
            or getattr(settings, "schema_registry_url", "")
            or ""
        )
        self._base = url.rstrip("/")
        self._timeout = float(timeout_s)
        self._token = token

    @property
    def configured(self) -> bool:
        return bool(self._base)

    def _client(self) -> httpx.Client:
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.Client(timeout=self._timeout, headers=headers)

    def _ccompat_url(self, path: str) -> str:
        suffix = path.lstrip("/")
        if "/ccompat" in self._base:
            return f"{self._base}/{suffix}"
        return f"{self._base}/apis/ccompat/v7/{suffix}"

    def list_subjects(self) -> list[str]:
        if not self.configured:
            return []
        with self._client() as client:
            r = client.get(self._ccompat_url("subjects"))
            if r.status_code >= 400:
                raise SchemaRegistryError(f"list_subjects: {r.status_code} {r.text}")
            data = r.json()
            return [str(s) for s in data] if isinstance(data, list) else []

    def latest_version(self, subject: str) -> dict[str, Any]:
        if not self.configured:
            raise SchemaRegistryError("schema registry url not configured")
        with self._client() as client:
            r = client.get(self._ccompat_url(f"subjects/{subject}/versions/latest"))
            if r.status_code == 404:
                raise SchemaRegistryError(f"subject {subject} not found")
            if r.status_code >= 400:
                raise SchemaRegistryError(f"latest_version: {r.status_code} {r.text}")
            return r.json()

    def list_versions(self, subject: str) -> list[int]:
        if not self.configured:
            return []
        with self._client() as client:
            r = client.get(self._ccompat_url(f"subjects/{subject}/versions"))
            if r.status_code >= 400:
                raise SchemaRegistryError(f"list_versions: {r.status_code} {r.text}")
            data = r.json()
            return [int(v) for v in data] if isinstance(data, list) else []

    def register_schema(
        self,
        subject: str,
        *,
        schema: str,
        schema_type: str = "AVRO",
        references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise SchemaRegistryError("schema registry url not configured")
        body: dict[str, Any] = {"schema": schema, "schemaType": schema_type}
        if references:
            body["references"] = list(references)
        with self._client() as client:
            r = client.post(
                self._ccompat_url(f"subjects/{subject}/versions"),
                json=body,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            )
            if r.status_code >= 400:
                raise SchemaRegistryError(
                    f"register_schema: {r.status_code} {r.text}"
                )
            return r.json()


_singleton: ApicurioSchemaRegistry | None = None


def get_schema_registry() -> ApicurioSchemaRegistry:
    global _singleton
    if _singleton is None:
        _singleton = ApicurioSchemaRegistry()
    return _singleton


__all__ = ["ApicurioSchemaRegistry", "SchemaRegistryError", "get_schema_registry"]
