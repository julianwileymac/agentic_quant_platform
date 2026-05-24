"""Content-addressable cassette stores."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def hash_request(
    *,
    method: str,
    url: str,
    body: bytes | None = None,
    key_id_scope: str | None = None,
) -> str:
    """Stable SHA-256 over (method, url, normalized body, key_id_scope)."""
    h = hashlib.sha256()
    h.update(method.upper().encode("utf-8"))
    h.update(b"\x00")
    h.update(url.encode("utf-8"))
    h.update(b"\x00")
    h.update(body if body else b"")
    h.update(b"\x00")
    h.update((key_id_scope or "").encode("utf-8"))
    return h.hexdigest()


@dataclass(slots=True)
class CassetteEntry:
    request_hash: str
    method: str
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    meta: dict[str, Any] = field(default_factory=dict)


class InMemoryCassetteStore:
    """Process-local cassette store for tests + offline laptop use."""

    def __init__(self) -> None:
        self._entries: dict[str, CassetteEntry] = {}
        self._lock = threading.RLock()

    def exists(self, request_hash: str) -> bool:
        with self._lock:
            return request_hash in self._entries

    def get(self, request_hash: str) -> CassetteEntry | None:
        with self._lock:
            return self._entries.get(request_hash)

    def put(self, entry: CassetteEntry) -> None:
        with self._lock:
            self._entries[entry.request_hash] = entry

    def delete(self, request_hash: str) -> None:
        with self._lock:
            self._entries.pop(request_hash, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class S3CassetteStore:
    """S3-backed content-addressable cassette store.

    Bucket layout::

        s3://{bucket}/{prefix}/{request_hash[:2]}/{request_hash}.cassette
        s3://{bucket}/{prefix}/{request_hash[:2]}/{request_hash}.meta.json

    The ``meta.json`` carries the original ``Retry-After``, ETag,
    timestamps, and a ``cassette_meta`` field that the operator can
    use for cassette-pinning regulatory backtests.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "aqp-replay-cache",
        s3_client: Any | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = s3_client or self._build_client()

    def exists(self, request_hash: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=self._cassette_key(request_hash),
            )
            return True
        except Exception:  # noqa: BLE001 — boto3 raises ClientError on 404
            return False

    def get(self, request_hash: str) -> CassetteEntry | None:
        try:
            obj = self._client.get_object(
                Bucket=self._bucket,
                Key=self._cassette_key(request_hash),
            )
            meta_obj = self._client.get_object(
                Bucket=self._bucket,
                Key=self._meta_key(request_hash),
            )
        except Exception:  # noqa: BLE001
            return None
        body = obj["Body"].read()
        meta = json.loads(meta_obj["Body"].read().decode("utf-8"))
        return CassetteEntry(
            request_hash=request_hash,
            method=meta.get("method", "GET"),
            url=meta.get("url", ""),
            status=int(meta.get("status", 200)),
            headers=dict(meta.get("headers", {})),
            body=body,
            meta=meta.get("cassette_meta", {}),
        )

    def put(self, entry: CassetteEntry) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._cassette_key(entry.request_hash),
                Body=entry.body,
            )
            self._client.put_object(
                Bucket=self._bucket,
                Key=self._meta_key(entry.request_hash),
                Body=json.dumps(
                    {
                        "method": entry.method,
                        "url": entry.url,
                        "status": entry.status,
                        "headers": entry.headers,
                        "cassette_meta": entry.meta,
                    }
                ).encode("utf-8"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not write cassette %s: %s", entry.request_hash, exc)

    def delete(self, request_hash: str) -> None:
        for key in (self._cassette_key(request_hash), self._meta_key(request_hash)):
            try:
                self._client.delete_object(Bucket=self._bucket, Key=key)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cassette_key(self, request_hash: str) -> str:
        return f"{self._prefix}/{request_hash[:2]}/{request_hash}.cassette"

    def _meta_key(self, request_hash: str) -> str:
        return f"{self._prefix}/{request_hash[:2]}/{request_hash}.meta.json"

    def _build_client(self) -> Any:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "boto3 required for S3CassetteStore; install aqp-ratelimit[replay]"
            ) from exc
        return boto3.client("s3")


__all__ = [
    "CassetteEntry",
    "InMemoryCassetteStore",
    "S3CassetteStore",
    "hash_request",
]
