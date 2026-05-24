"""Apicurio-compatible Avro codec (Confluent wire format).

Schemas are registered on startup from local ``.avsc`` files. Each record is
prefixed with ``0x00`` + 4 byte big-endian schema id so Flink jobs using the
Confluent deserializer can consume them transparently.
"""

from __future__ import annotations

import io
import json
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import httpx
from fastavro import parse_schema, schemaless_writer

logger = logging.getLogger(__name__)


_CONFLUENT_MAGIC = 0


@dataclass
class RegisteredSchema:
    global_id: int
    schema: Dict[str, Any]


class AvroCodec:
    """Apicurio-backed schema registry client + Avro encoder."""

    def __init__(
        self,
        registry_url: str,
        *,
        group: str = "default",
        timeout: float = 10.0,
        auto_register: bool = True,
    ) -> None:
        self._base = registry_url.rstrip("/")
        self._group = group
        self._auto_register = auto_register
        self._client = httpx.Client(timeout=timeout)
        self._by_name: Dict[str, RegisteredSchema] = {}

    def close(self) -> None:
        self._client.close()

    def register(self, name: str, schema: Dict[str, Any]) -> RegisteredSchema:
        """Ensure the schema is registered; returns the registered record."""

        if name in self._by_name:
            return self._by_name[name]

        if self._auto_register:
            self._upload(name, schema)

        url = f"{self._base}/groups/{self._group}/artifacts/{name}"
        meta_res = self._client.get(f"{url}/meta")
        if meta_res.status_code == 404 and self._auto_register:
            self._upload(name, schema)
            meta_res = self._client.get(f"{url}/meta")
        meta_res.raise_for_status()
        meta = meta_res.json()
        schema_res = self._client.get(url)
        schema_res.raise_for_status()
        registered = RegisteredSchema(
            global_id=int(meta.get("globalId", meta.get("contentId", 0))),
            schema=parse_schema(schema_res.json()),
        )
        self._by_name[name] = registered
        return registered

    def register_from_file(self, name: str, path: str | Path) -> RegisteredSchema:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.register(name, data)

    def encode(self, name: str, record: Dict[str, Any]) -> bytes:
        registered = self._by_name.get(name)
        if registered is None:
            raise KeyError(
                f"schema {name!r} has not been registered yet; call register() first",
            )
        buf = io.BytesIO()
        buf.write(struct.pack(">bI", _CONFLUENT_MAGIC, registered.global_id))
        schemaless_writer(buf, registered.schema, record)
        return buf.getvalue()

    def _upload(self, name: str, schema: Dict[str, Any]) -> None:
        url = f"{self._base}/groups/{self._group}/artifacts"
        try:
            self._client.post(
                url,
                json=schema,
                params={"ifExists": "RETURN_OR_UPDATE"},
                headers={
                    "X-Registry-ArtifactId": name,
                    "X-Registry-ArtifactType": "AVRO",
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("schema upload for %s failed: %s", name, exc)


__all__ = ["AvroCodec", "RegisteredSchema"]
