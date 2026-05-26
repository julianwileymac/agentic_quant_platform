"""RFC 3161 Time Stamping Authority transparency anchor sink (Phase 7 §10.1).

RFC 3161 lets a Time Stamping Authority (TSA) cryptographically anchor
a digest at a specific point in time. The TSA returns a signed
``TimeStampResp`` blob; AQP persists it as the verification handle.
This is the lowest-friction sink for ``silo-reg``-on-prem cells where
neither sigstore (Internet egress) nor AWS QLDB are options.

The sink uses the standard RFC 3161 HTTP transport. The TSA URL +
optional client cert come from :class:`CredentialResolver` under
``CredentialKey('rfc3161', 'tsa:<alias>')``. The ``rfc3161`` Python
package is optional; the sink raises a clear error if it's missing.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from aqp.audit.protocol import AnchorRecord, TransparencyAnchorSink

logger = logging.getLogger(__name__)


class Rfc3161TsaSink(TransparencyAnchorSink):
    """Submit audit-segment tip-hashes to an external RFC 3161 TSA."""

    sink_kind = "rfc3161"
    sink_alias = "Rfc3161TsaSink"

    def __init__(
        self,
        tsa_alias: str | None = None,
        tsa_url: str | None = None,
    ) -> None:
        try:
            from aqp.config import settings

            self._tsa_alias = tsa_alias or getattr(
                settings, "audit_rfc3161_tsa_alias", "default"
            )
            self._tsa_url = tsa_url or getattr(settings, "audit_rfc3161_tsa_url", "")
        except Exception:  # noqa: BLE001 - defensive
            self._tsa_alias = tsa_alias or "default"
            self._tsa_url = tsa_url or ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_credentials(self) -> dict[str, str]:
        from aqp.credentials import CredentialKey, get_resolver

        creds = get_resolver().resolve(
            CredentialKey("rfc3161", f"tsa:{self._tsa_alias}"),
            default={
                "url": self._tsa_url,
                "client_cert_pem": "",
                "client_key_pem": "",
                "ca_bundle_pem": "",
            },
        )
        return {
            "url": str(creds.get("url") or self._tsa_url or ""),
            "client_cert_pem": str(creds.get("client_cert_pem") or ""),
            "client_key_pem": str(creds.get("client_key_pem") or ""),
            "ca_bundle_pem": str(creds.get("ca_bundle_pem") or ""),
        }

    def _client(self):
        """Return an rfc3161ng RemoteTimestamper instance, or raise."""
        try:
            from rfc3161ng import RemoteTimestamper  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Rfc3161TsaSink requires the 'rfc3161ng' package. Install with "
                "``pip install agentic-quant-platform[audit-rfc3161]``."
            ) from exc
        creds = self._resolve_credentials()
        if not creds["url"]:
            raise RuntimeError(
                "Rfc3161TsaSink.tsa_url is empty — set "
                "``AQP_AUDIT_RFC3161_TSA_URL`` or seed the credential "
                f"``CredentialKey('rfc3161', 'tsa:{self._tsa_alias}')`` "
                "with a ``url`` field before anchoring."
            )
        kwargs: dict[str, Any] = {"url": creds["url"]}
        if creds["client_cert_pem"] and creds["client_key_pem"]:
            kwargs["certificate"] = creds["client_cert_pem"]
            kwargs["private_key"] = creds["client_key_pem"]
        return RemoteTimestamper(**kwargs)

    @staticmethod
    def _digest(record: AnchorRecord) -> bytes:
        """SHA-256 over the canonical fields. The TSA only sees the digest."""
        import hashlib
        import json

        payload = json.dumps(
            {
                "cell_id": record.cell_id,
                "segment_start_ts": record.segment_start_ts.isoformat(),
                "segment_end_ts": record.segment_end_ts.isoformat(),
                "prev_tip_hash": (
                    record.prev_tip_hash.hex() if record.prev_tip_hash else None
                ),
                "tip_hash": record.tip_hash.hex(),
                "iceberg_snapshot_id": record.iceberg_snapshot_id,
                "s3_manifest_uri": record.s3_manifest_uri,
                "extra": dict(record.extra),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).digest()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def anchor(self, record: AnchorRecord) -> str:
        """Submit the segment digest to the TSA; return the b64'd TimeStampResp."""
        client = self._client()
        digest = self._digest(record)
        try:
            tsr_bytes = client.timestamp(data=digest)
        except Exception as exc:  # noqa: BLE001 - vendor-specific exceptions
            raise RuntimeError(
                f"RFC 3161 anchor failed: {type(exc).__name__}: {exc}"
            ) from exc
        # ``timestamp`` may return the raw TimeStampResp blob (bytes)
        # or a wrapper object; coerce to bytes defensively.
        if not isinstance(tsr_bytes, (bytes, bytearray)):
            tsr_bytes = getattr(tsr_bytes, "as_der", lambda: b"")() or b""
        if not tsr_bytes:
            raise RuntimeError("RFC 3161 TSA returned an empty TimeStampResp")
        return base64.b64encode(bytes(tsr_bytes)).decode("ascii")

    def verify(self, record: AnchorRecord, handle: str) -> bool:
        """Verify the stored TimeStampResp against the recomputed digest."""
        try:
            from rfc3161ng import RemoteTimestamper, check_timestamp  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return False
        try:
            tsr_bytes = base64.b64decode(handle)
        except Exception:  # noqa: BLE001 - defensive
            return False
        client = self._client()
        digest = self._digest(record)
        try:
            return bool(check_timestamp(tsr_bytes, data=digest))
        except Exception as exc:  # noqa: BLE001 - vendor-specific
            logger.warning("RFC 3161 verify failed: %s", exc)
            return False
