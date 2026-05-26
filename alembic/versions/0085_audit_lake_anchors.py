"""Audit lake segment anchors (Phase 7 §10.1).

Revision ID: 0085_audit_lake_anchors
Revises: 0084_mcp_tool_versioning
Create Date: 2026-05-25

Adds two new tables that compose with the Phase 6 audit/ MinIO
Object Lock COMPLIANCE storage:

- ``audit_lake_segments`` — one row per closed audit-log segment that
  the hourly Celery beat job (``aqp.tasks.audit_lake_tasks.flush``)
  copied to Iceberg + the per-cell MinIO ``audit/`` prefix. Carries
  the segment's start/end timestamps, the previous-segment tip-hash,
  the current segment tip-hash, the Iceberg snapshot id, and the
  s3:// URI of the manifest.
- ``audit_lake_anchors`` — one row per ``(segment_id, sink_kind)``
  pair recording the transparency-log verification handle (Rekor
  entry UUID, QLDB document id, base64 TimeStampResp). A segment can
  be anchored to MULTIPLE sinks (e.g. Rekor + RFC 3161 TSA for
  belt-and-braces) so the table is intentionally not unique on
  ``segment_id`` alone.

Per AGENTS rule 6: immutable once shipped. Carry-on follow-ups land in
later migrations (the next is ``0086_lineage_cell_id``).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085_audit_lake_anchors"
down_revision = "0084_mcp_tool_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_lake_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cell_id", sa.String(120), nullable=False),
        # Wall-clock boundary of the segment. The flush job aligns
        # segments to UTC hour boundaries by default; operators can
        # widen via ``settings.audit_lake_segment_minutes``.
        sa.Column("segment_start_ts", sa.DateTime, nullable=False),
        sa.Column("segment_end_ts", sa.DateTime, nullable=False),
        # Hash-chain links between segments. ``prev_segment_tip_hash``
        # is NULL for the very first segment per cell; thereafter it
        # equals the previous segment's ``segment_tip_hash`` for an
        # intact chain.
        sa.Column("prev_segment_tip_hash", sa.LargeBinary, nullable=True),
        sa.Column("segment_tip_hash", sa.LargeBinary, nullable=False),
        # How many audit_log rows the segment covers — used as a
        # cheap parity check during reconstruction.
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        # Iceberg + S3 evidence of materialisation. Both fields are
        # mandatory once a row reaches ``state='flushed'``; they may
        # be NULL during the brief in-flight window.
        sa.Column("iceberg_snapshot_id", sa.String(120), nullable=True),
        sa.Column("s3_manifest_uri", sa.String(512), nullable=True),
        # Lifecycle state. ``planned`` -> ``flushed`` -> ``anchored``.
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="planned",
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("flushed_at", sa.DateTime, nullable=True),
        sa.Column("anchored_at", sa.DateTime, nullable=True),
        # Arbitrary cell-side metadata (chain context, signing key id).
        sa.Column("meta_json", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "cell_id",
            "segment_start_ts",
            name="uq_audit_lake_segments_cell_window",
        ),
    )
    op.create_index(
        "ix_audit_lake_segments_cell_state",
        "audit_lake_segments",
        ["cell_id", "state"],
    )
    op.create_index(
        "ix_audit_lake_segments_state_created",
        "audit_lake_segments",
        ["state", "created_at"],
    )

    op.create_table(
        "audit_lake_anchors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "segment_id",
            sa.String(36),
            sa.ForeignKey("audit_lake_segments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The sink that produced this anchor. Matches the
        # ``TransparencyAnchorSink.sink_kind`` value: ``rekor`` /
        # ``qldb`` / ``rfc3161``.
        sa.Column("sink_kind", sa.String(32), nullable=False),
        # Sink-specific verification handle. Rekor returns a UUID;
        # QLDB returns a document id; RFC 3161 returns the base64'd
        # TimeStampResp blob. We size the column generously for the
        # RFC 3161 case where the blob can be several KB.
        sa.Column("verification_handle", sa.Text, nullable=False),
        # Optional URL the operator can paste into a browser to view
        # the entry (Rekor entry URL, QLDB console deep link).
        sa.Column("verification_url", sa.String(512), nullable=True),
        sa.Column(
            "anchored_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Verification cache. ``last_verified_at`` + ``last_verified_ok``
        # let an auditor see when the anchor was last re-validated.
        sa.Column("last_verified_at", sa.DateTime, nullable=True),
        sa.Column("last_verified_ok", sa.Boolean, nullable=True),
        sa.Column("meta_json", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "segment_id", "sink_kind", name="uq_audit_lake_anchors_segment_sink"
        ),
    )
    op.create_index(
        "ix_audit_lake_anchors_sink_kind",
        "audit_lake_anchors",
        ["sink_kind"],
    )
    op.create_index(
        "ix_audit_lake_anchors_anchored_at",
        "audit_lake_anchors",
        ["anchored_at"],
    )


def downgrade() -> None:
    for ix in (
        "ix_audit_lake_anchors_anchored_at",
        "ix_audit_lake_anchors_sink_kind",
    ):
        op.drop_index(ix, table_name="audit_lake_anchors")
    op.drop_table("audit_lake_anchors")
    for ix in (
        "ix_audit_lake_segments_state_created",
        "ix_audit_lake_segments_cell_state",
    ):
        op.drop_index(ix, table_name="audit_lake_segments")
    op.drop_table("audit_lake_segments")
