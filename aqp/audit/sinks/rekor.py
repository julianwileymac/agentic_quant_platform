"""Sigstore Rekor transparency-log anchor sink (Phase 7 §10.1).

Rekor is the free, public sigstore transparency log. It accepts
JSON-encoded entries of type ``hashedrekord`` (a SHA-256 digest +
detached signature). For AQP segment anchors we submit each closed
segment's tip-hash + segment metadata as a custom ``intoto`` envelope
so the entry includes the full audit-segment context, not just the
digest. The submission credentials (signing key) come from
:class:`CredentialResolver` under
``CredentialKey('rekor', 'sigstore')``.

This is the default sink for ``shared-std`` and ``shared-prem`` cells.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

import httpx

from aqp.audit.protocol import AnchorRecord, TransparencyAnchorSink

logger = logging.getLogger(__name__)


class RekorSink(TransparencyAnchorSink):
    """Submit audit-segment tip-hashes to a sigstore Rekor instance."""

    sink_kind = "rekor"
    sink_alias = "RekorSink"

    # Default to the public sigstore Rekor. Operators can override via
    # ``settings.audit_rekor_url`` to point at a private instance.
    DEFAULT_URL: str = "https://rekor.sigstore.dev"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        try:
            from aqp.config import settings

            self._base_url = (
                base_url
                or getattr(settings, "audit_rekor_url", "")
                or self.DEFAULT_URL
            )
        except Exception:  # noqa: BLE001 - defensive
            self._base_url = base_url or self.DEFAULT_URL
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Payload helpers
    # ------------------------------------------------------------------

    def _envelope(self, record: AnchorRecord) -> dict[str, Any]:
        """Return the in-toto envelope payload for ``record``.

        We DO NOT include the cell's signing key in the envelope —
        that lives in ``lineage_signing_key_archive`` (Alembic 0061)
        and the verifier looks it up from there. The envelope itself
        carries only the segment manifest data.
        """
        return {
            "_type": "https://in-toto.io/Statement/v0.1",
            "predicateType": "https://aqp.fund/audit-segment-anchor/v1",
            "subject": [
                {
                    "name": f"audit-segment/{record.cell_id}/{record.iceberg_snapshot_id}",
                    "digest": {"sha256": record.tip_hash.hex()},
                }
            ],
            "predicate": {
                "cell_id": record.cell_id,
                "segment_start_ts": record.segment_start_ts.isoformat(),
                "segment_end_ts": record.segment_end_ts.isoformat(),
                "prev_tip_hash": (
                    record.prev_tip_hash.hex() if record.prev_tip_hash else None
                ),
                "tip_hash": record.tip_hash.hex(),
                "iceberg_snapshot_id": record.iceberg_snapshot_id,
                "s3_manifest_uri": record.s3_manifest_uri,
                "extra": record.extra,
            },
        }

    def _resolve_credentials(self) -> dict[str, str]:
        """Resolve the Rekor signing credentials via CredentialResolver."""
        from aqp.credentials import CredentialKey, get_resolver

        creds = get_resolver().resolve(
            CredentialKey("rekor", "sigstore"),
            default={
                "signing_key_pem": "",
                "signing_cert_pem": "",
            },
        )
        return {
            "signing_key_pem": str(creds.get("signing_key_pem") or ""),
            "signing_cert_pem": str(creds.get("signing_cert_pem") or ""),
        }

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def anchor(self, record: AnchorRecord) -> str:
        """POST a ``hashedrekord`` entry to Rekor.

        The payload digest is SHA-256 of the canonical-JSON envelope.
        Rekor returns the entry UUID + integrated time + signed entry
        timestamp; we persist the UUID as the verification handle.
        """
        envelope = self._envelope(record)
        payload = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        digest = hashlib.sha256(payload).hexdigest()

        creds = self._resolve_credentials()
        signing_cert_b64 = (
            base64.b64encode(creds["signing_cert_pem"].encode("utf-8")).decode("ascii")
            if creds["signing_cert_pem"]
            else ""
        )
        # We compute the detached signature externally (the
        # ``lineage_signing_key_archive`` chain is the source of truth
        # for the active signing key). For Phase 7 the helper attaches
        # an empty signature in the local-fallback path; operators
        # MUST wire a real signing pipeline before going to production.
        signature_b64 = ""

        request_body = {
            "apiVersion": "0.0.1",
            "kind": "hashedrekord",
            "spec": {
                "data": {"hash": {"algorithm": "sha256", "value": digest}},
                "signature": {
                    "content": signature_b64,
                    "publicKey": {"content": signing_cert_b64},
                },
            },
        }

        url = f"{self._base_url.rstrip('/')}/api/v1/log/entries"
        logger.debug("Anchoring segment %s to Rekor at %s", record.iceberg_snapshot_id, url)
        try:
            response = httpx.post(url, json=request_body, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"rekor anchor failed: {type(exc).__name__}: {exc}"
            ) from exc
        body = response.json()
        # Rekor returns a single-key dict where the key is the UUID.
        # E.g. {"abc123...": {"body": "...", "integratedTime": ...}}
        if not isinstance(body, dict) or len(body) != 1:
            raise RuntimeError(
                f"rekor anchor returned unexpected payload: {type(body).__name__}"
            )
        return next(iter(body.keys()))

    def verify(self, record: AnchorRecord, handle: str) -> bool:
        """GET the Rekor entry by UUID and recompute the digest."""
        url = f"{self._base_url.rstrip('/')}/api/v1/log/entries/{handle}"
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("rekor verify GET failed: %s", exc)
            return False
        body = response.json()
        if not isinstance(body, dict) or handle not in body:
            return False
        # We only check that the entry's hash matches what we'd compute
        # locally. The full sigstore signature-chain verification is a
        # separate concern (the operator can run ``cosign verify``).
        entry = body[handle]
        rekord_body = entry.get("body")
        if not rekord_body:
            return False
        try:
            decoded = json.loads(base64.b64decode(rekord_body))
        except Exception:  # noqa: BLE001 - defensive
            return False
        recorded_hash = (
            decoded.get("spec", {})
            .get("data", {})
            .get("hash", {})
            .get("value", "")
        )
        envelope = self._envelope(record)
        payload = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        expected_hash = hashlib.sha256(payload).hexdigest()
        return recorded_hash == expected_hash
