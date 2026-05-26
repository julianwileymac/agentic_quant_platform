"""AWS QLDB transparency-log anchor sink (Phase 7 §10.1).

QLDB (Quantum Ledger Database) is an AWS-managed, cryptographically
verifiable ledger. For ``silo-reg``-on-AWS cells it's the lowest-
friction private transparency log: no extra infrastructure, the
journal itself is hash-chained, and Amazon publishes verification
APIs.

Credentials resolve through :class:`CredentialResolver` under
``CredentialKey('qldb', 'ledger:<name>')``. The ``boto3`` dependency
is optional — the sink raises a clear error at construction time if
the SDK isn't installed.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.audit.protocol import AnchorRecord, TransparencyAnchorSink

logger = logging.getLogger(__name__)


class QLDBSink(TransparencyAnchorSink):
    """Submit audit-segment tip-hashes to AWS QLDB.

    Each segment lands as one document in the ``audit_segment_anchors``
    table of the configured ledger. The verification handle returned to
    the caller is the QLDB document id; QLDB internally indexes its
    journal so any document id can be retrieved + verified via the
    ``GetDigest``/``GetRevision`` APIs.
    """

    sink_kind = "qldb"
    sink_alias = "QLDBSink"

    def __init__(
        self,
        ledger_name: str | None = None,
        region_name: str | None = None,
        table_name: str = "audit_segment_anchors",
    ) -> None:
        try:
            from aqp.config import settings

            self._ledger_name = ledger_name or getattr(
                settings, "audit_qldb_ledger_name", ""
            )
            self._region_name = region_name or getattr(
                settings, "audit_qldb_region", ""
            )
        except Exception:  # noqa: BLE001 - defensive
            self._ledger_name = ledger_name or ""
            self._region_name = region_name or ""
        self._table_name = table_name
        if not self._ledger_name:
            logger.warning(
                "QLDBSink instantiated without ledger_name; anchor() will fail"
            )

    # ------------------------------------------------------------------
    # Payload helpers
    # ------------------------------------------------------------------

    def _document(self, record: AnchorRecord) -> dict[str, Any]:
        return {
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
        }

    def _driver(self):
        """Return the pyqldb QldbDriver, raising a clear error if missing."""
        try:
            from pyqldb.driver.qldb_driver import QldbDriver  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "QLDBSink requires the 'pyqldb' package. Install with "
                "``pip install agentic-quant-platform[audit-qldb]``."
            ) from exc
        kwargs: dict[str, Any] = {"ledger_name": self._ledger_name}
        if self._region_name:
            kwargs["region_name"] = self._region_name
        return QldbDriver(**kwargs)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def anchor(self, record: AnchorRecord) -> str:
        """INSERT the document into the QLDB ledger; return the doc id."""
        if not self._ledger_name:
            raise RuntimeError(
                "QLDBSink.ledger_name is empty — set "
                "``AQP_AUDIT_QLDB_LEDGER_NAME`` before anchoring."
            )
        driver = self._driver()
        doc = self._document(record)

        def _txn(txn) -> str:  # type: ignore[no-untyped-def]
            # PartiQL INSERT returns metadata including the documentId.
            cursor = txn.execute_statement(
                f"INSERT INTO {self._table_name} ?", doc
            )
            row = next(cursor, None)
            if row is None or "documentId" not in row:
                raise RuntimeError(
                    "QLDB insert returned no documentId"
                )
            return str(row["documentId"])

        doc_id = driver.execute_lambda(_txn)
        logger.debug(
            "Anchored segment %s into QLDB ledger %s document %s",
            record.iceberg_snapshot_id,
            self._ledger_name,
            doc_id,
        )
        return doc_id

    def verify(self, record: AnchorRecord, handle: str) -> bool:
        """SELECT the document by id and compare to ``record``."""
        if not self._ledger_name:
            return False
        driver = self._driver()
        expected = self._document(record)

        def _txn(txn) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
            cursor = txn.execute_statement(
                f"SELECT * FROM _ql_committed_{self._table_name} "
                "WHERE metadata.id = ?",
                handle,
            )
            row = next(cursor, None)
            return dict(row) if row is not None else None

        committed = driver.execute_lambda(_txn)
        if not committed:
            return False
        data = committed.get("data", {})
        # Compare the digest-relevant fields. We don't compare
        # ``extra`` strictly because operators may have appended
        # safe metadata post-anchor.
        keys = (
            "cell_id",
            "segment_start_ts",
            "segment_end_ts",
            "prev_tip_hash",
            "tip_hash",
            "iceberg_snapshot_id",
            "s3_manifest_uri",
        )
        return all(data.get(k) == expected.get(k) for k in keys)
