"""Thin Apicurio Registry client.

We speak the REST v2 API directly rather than the Confluent-compat shim so
we can take advantage of the group/artifact model when organising schemas
for multiple pipelines in the same cluster.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

CONFLUENT_MAGIC = 0


@dataclass
class RegisteredSchema:
    global_id: int
    schema: Dict[str, Any]


class ApicurioClient:
    """Synchronous Apicurio Registry REST v2 client."""

    def __init__(
        self,
        base_url: str = "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2",
        group: str = "default",
        *,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.group = group
        self._client = httpx.Client(timeout=timeout)
        self._cache_by_name: Dict[str, RegisteredSchema] = {}
        self._cache_by_id: Dict[int, RegisteredSchema] = {}

    def __enter__(self) -> "ApicurioClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------

    def register(self, name: str, schema: Dict[str, Any], *, if_exists: str = "RETURN_OR_UPDATE") -> RegisteredSchema:
        """Create or update an artifact and cache the parsed Avro schema."""
        from fastavro import parse_schema

        url = f"{self.base_url}/groups/{self.group}/artifacts"
        params = {"ifExists": if_exists}
        headers = {
            "Content-Type": "application/json",
            "X-Registry-ArtifactId": name,
            "X-Registry-ArtifactType": "AVRO",
        }
        res = self._client.post(url, params=params, headers=headers, json=schema)
        res.raise_for_status()
        meta = res.json()
        registered = RegisteredSchema(
            global_id=int(meta.get("globalId", meta.get("contentId", 0))),
            schema=parse_schema(schema),
        )
        self._cache_by_name[name] = registered
        self._cache_by_id[registered.global_id] = registered
        return registered

    def get_by_name(self, name: str) -> RegisteredSchema:
        from fastavro import parse_schema

        if name in self._cache_by_name:
            return self._cache_by_name[name]
        schema_res = self._client.get(f"{self.base_url}/groups/{self.group}/artifacts/{name}")
        schema_res.raise_for_status()
        meta_res = self._client.get(f"{self.base_url}/groups/{self.group}/artifacts/{name}/meta")
        meta_res.raise_for_status()
        meta = meta_res.json()
        registered = RegisteredSchema(
            global_id=int(meta.get("globalId", meta.get("contentId", 0))),
            schema=parse_schema(schema_res.json()),
        )
        self._cache_by_name[name] = registered
        self._cache_by_id[registered.global_id] = registered
        return registered

    def get_by_id(self, schema_id: int) -> RegisteredSchema:
        from fastavro import parse_schema

        if schema_id in self._cache_by_id:
            return self._cache_by_id[schema_id]
        res = self._client.get(f"{self.base_url}/ids/globalIds/{schema_id}")
        res.raise_for_status()
        registered = RegisteredSchema(global_id=schema_id, schema=parse_schema(res.json()))
        self._cache_by_id[schema_id] = registered
        return registered

    # ------------------------------------------------------------------
    # Encoding helpers - Confluent-compatible wire format
    # ------------------------------------------------------------------

    def encode(self, name: str, record: Dict[str, Any]) -> bytes:
        from fastavro import schemaless_writer

        registered = self.get_by_name(name)
        buf = io.BytesIO()
        buf.write(struct.pack(">bI", CONFLUENT_MAGIC, registered.global_id))
        schemaless_writer(buf, registered.schema, record)
        return buf.getvalue()

    def decode(self, payload: bytes) -> Dict[str, Any]:
        from fastavro import schemaless_reader

        if not payload:
            raise ValueError("empty payload")
        buf = io.BytesIO(payload)
        magic = buf.read(1)[0]
        if magic != CONFLUENT_MAGIC:
            raise ValueError(f"unsupported magic byte 0x{magic:02x}")
        (schema_id,) = struct.unpack(">I", buf.read(4))
        registered = self.get_by_id(schema_id)
        return schemaless_reader(buf, registered.schema)

    def load_local(self, name: str, path: str) -> RegisteredSchema:
        """Register from an on-disk .avsc file."""
        with open(path, "r", encoding="utf-8") as fh:
            return self.register(name, json.load(fh))
