"""Avro codec backed by the Apicurio Registry REST v2 API."""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from typing import Any, Dict

import httpx
from fastavro import parse_schema, schemaless_reader

_CONFLUENT_MAGIC = 0


@dataclass
class RegisteredSchema:
    global_id: int
    schema: Dict[str, Any]


class AvroCodec:
    def __init__(self, registry_url: str, group: str = "default", timeout: float = 10.0):
        self._base = registry_url.rstrip("/")
        self._group = group
        self._client = httpx.AsyncClient(timeout=timeout)
        self._cache: Dict[int, RegisteredSchema] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _fetch_by_id(self, schema_id: int) -> RegisteredSchema:
        if schema_id in self._cache:
            return self._cache[schema_id]
        # Apicurio ccompat-style schema fetch by global content id
        res = await self._client.get(f"{self._base}/ids/globalIds/{schema_id}")
        res.raise_for_status()
        registered = RegisteredSchema(global_id=schema_id, schema=parse_schema(res.json()))
        self._cache[schema_id] = registered
        return registered

    async def decode(self, payload: bytes) -> Dict[str, Any]:
        if not payload:
            raise ValueError("empty payload")
        buf = io.BytesIO(payload)
        magic = buf.read(1)[0]
        if magic != _CONFLUENT_MAGIC:
            raise ValueError(f"unsupported magic byte 0x{magic:02x}")
        (schema_id,) = struct.unpack(">I", buf.read(4))
        registered = await self._fetch_by_id(schema_id)
        return schemaless_reader(buf, registered.schema)
