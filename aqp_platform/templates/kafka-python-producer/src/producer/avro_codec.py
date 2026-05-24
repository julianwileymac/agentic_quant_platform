"""Avro codec that talks to Apicurio Registry over its REST v2 API."""

from __future__ import annotations

import io
import logging
import struct
from dataclasses import dataclass
from typing import Any, Dict

import httpx
from fastavro import parse_schema, schemaless_reader, schemaless_writer

logger = logging.getLogger(__name__)

# Confluent-compatible wire format header used by Apicurio when ccompat is on.
#   magic byte (0) + 4-byte big-endian schema id + Avro payload
_CONFLUENT_MAGIC = 0


@dataclass
class RegisteredSchema:
    global_id: int
    schema: Dict[str, Any]


class AvroCodec:
    """Minimal Avro encode/decode + Apicurio Registry client."""

    def __init__(
        self,
        registry_url: str,
        group: str = "default",
        timeout: float = 10.0,
    ) -> None:
        self._base = registry_url.rstrip("/")
        self._group = group
        self._client = httpx.Client(timeout=timeout)
        self._by_name: Dict[str, RegisteredSchema] = {}
        self._by_id: Dict[int, RegisteredSchema] = {}

    def close(self) -> None:
        self._client.close()

    def load_schema(self, name: str) -> RegisteredSchema:
        if name in self._by_name:
            return self._by_name[name]
        url = f"{self._base}/groups/{self._group}/artifacts/{name}"
        meta_url = f"{url}/meta"
        schema_res = self._client.get(url)
        schema_res.raise_for_status()
        meta_res = self._client.get(meta_url)
        meta_res.raise_for_status()
        meta = meta_res.json()
        registered = RegisteredSchema(
            global_id=int(meta.get("globalId", meta.get("contentId", 0))),
            schema=parse_schema(schema_res.json()),
        )
        self._by_name[name] = registered
        self._by_id[registered.global_id] = registered
        return registered

    def encode(self, name: str, record: Dict[str, Any]) -> bytes:
        registered = self.load_schema(name)
        buf = io.BytesIO()
        buf.write(struct.pack(">bI", _CONFLUENT_MAGIC, registered.global_id))
        schemaless_writer(buf, registered.schema, record)
        return buf.getvalue()

    def decode(self, payload: bytes) -> Dict[str, Any]:
        if not payload:
            raise ValueError("empty payload")
        buf = io.BytesIO(payload)
        magic = buf.read(1)[0]
        if magic != _CONFLUENT_MAGIC:
            raise ValueError(f"unsupported magic byte 0x{magic:02x}")
        (schema_id,) = struct.unpack(">I", buf.read(4))
        registered = self._by_id.get(schema_id)
        if registered is None:
            raise KeyError(
                f"schema id {schema_id} not loaded; call load_schema() first"
            )
        return schemaless_reader(buf, registered.schema)


def load_schema(registry_url: str, group: str, name: str) -> RegisteredSchema:
    """Convenience for one-off schema fetches."""
    codec = AvroCodec(registry_url, group=group)
    try:
        return codec.load_schema(name)
    finally:
        codec.close()
