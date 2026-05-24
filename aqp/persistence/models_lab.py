"""Data Lab ORM models — ``lab_graphs``, ``lab_runs``, ``lab_node_runs``,
``lab_artifacts``, ``lab_snippets``, ``lab_labels``, ``lab_notes``,
``lab_paper_chunks``.

These rows back the four-mode Data Lab page. They live alongside (not
in place of) the existing :mod:`aqp.persistence.models_analysis`,
:mod:`aqp.persistence.models_workflows`, and
:mod:`aqp.persistence.models_rl` tables — the Data Lab compiler maps
each ``GraphSpec`` execution onto one or more of those existing
runtimes and joins the resulting run row by ``workflow_run_id`` /
``analysis_run_id`` / ``rl_run_id`` on :class:`LabRun`.

AGENTS rules honoured:

- Rule 34 — every run-producing table carries ``experiment_id`` +
  ``test_id`` FKs so :class:`aqp.persistence.ledger.LedgerWriter` can
  stamp them from the active :class:`RequestContext`.
- Rule 5 — inter-node frames pass via ``output_locator`` URIs
  (MinIO / Iceberg / Redis), never pickled ORM through Celery.
- Rule 7 — these models are loaded by importing this module; the
  Settings boot path stays untouched.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Mode + status whitelists (mirrored as CHECK constraints in migration 0057)
# ---------------------------------------------------------------------------

LAB_MODES: tuple[str, ...] = ("eda", "testing", "evaluation", "simulation")
LAB_RUN_STATUSES: tuple[str, ...] = (
    "pending",
    "queued",
    "running",
    "done",
    "error",
    "cancelled",
    "halted",
)
LAB_NODE_STATUSES: tuple[str, ...] = (
    "pending",
    "queued",
    "running",
    "done",
    "error",
    "cached",
    "skipped",
)
LAB_LABEL_KINDS: tuple[str, ...] = (
    "support_resistance",
    "trendline",
    "swing",
    "regime_band",
    "pattern",
    "order_event",
    "annotation",
)
LAB_NOTE_TARGETS: tuple[str, ...] = (
    "graph",
    "run",
    "node_run",
    "label",
    "paper_chunk",
    "snippet",
)
LAB_SNIPPET_LANGS: tuple[str, ...] = ("python", "sql")


# ---------------------------------------------------------------------------
# 1. lab_graphs
# ---------------------------------------------------------------------------


class LabGraph(Base):
    """Content-addressed GraphSpec document.

    The Pydantic :class:`aqp.lab.schema.GraphSpec` is canonical-JSON'd,
    SHA256'd, and stored on ``content_hash`` (mirrors
    :meth:`WorkflowSpec.snapshot_hash`). Together with
    ``data_snapshot`` + ``code_snapshot``, the triple is the
    reproducibility contract.
    """

    __tablename__ = "lab_graphs"

    id = Column(String(36), primary_key=True, default=_uuid)
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    mode = Column(String(24), nullable=False, index=True)
    spec = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=False, index=True)
    parent_graph_id = Column(
        String(36),
        ForeignKey("lab_graphs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    data_snapshot = Column(JSON, nullable=False, default=dict)
    code_snapshot = Column(String(64), nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)

    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    runs = relationship(
        "LabRun",
        back_populates="graph",
        cascade="all,delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            f"mode IN ({', '.join(repr(m) for m in LAB_MODES)})",
            name="ck_lab_graphs_mode",
        ),
        UniqueConstraint(
            "lab_id", "content_hash", name="uq_lab_graphs_lab_content_hash"
        ),
    )


Index(
    "ix_lab_graphs_lab_mode",
    LabGraph.lab_id,
    LabGraph.mode,
)


# ---------------------------------------------------------------------------
# 2. lab_runs
# ---------------------------------------------------------------------------


class LabRun(Base):
    """One :meth:`LabRuntime.submit_run` invocation."""

    __tablename__ = "lab_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    graph_id = Column(
        String(36),
        ForeignKey("lab_graphs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # AGENTS rule 34 — stamped from RequestContext by LedgerWriter.
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("aqp_tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    mode = Column(String(24), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    session_id = Column(String(120), nullable=True, index=True)
    task_id = Column(String(120), nullable=True, index=True)
    celery_root_id = Column(String(120), nullable=True)
    dagster_run_id = Column(String(120), nullable=True)

    # Soft FKs to existing runtime ledger tables — the Data Lab
    # compiler keeps the row pointer to the runtime row it dispatched
    # to so cross-runtime joins stay one-hop.
    workflow_run_id = Column(String(36), nullable=True, index=True)
    analysis_run_id = Column(String(36), nullable=True, index=True)
    rl_run_id = Column(String(36), nullable=True, index=True)

    mlflow_run_id = Column(String(120), nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)

    metrics = Column(JSON, nullable=False, default=dict)
    result_summary = Column(JSON, nullable=False, default=dict)
    data_snapshot = Column(JSON, nullable=False, default=dict)
    code_snapshot = Column(String(64), nullable=True)

    # Required honest count for Deflated Sharpe Ratio (AGENTS plan §13).
    total_trials_searched = Column(Integer, nullable=False, default=1)

    error = Column(Text, nullable=True)
    halted = Column(Boolean, nullable=False, default=False)
    halt_reason = Column(String(240), nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)

    graph = relationship("LabGraph", back_populates="runs")
    node_runs = relationship(
        "LabNodeRun",
        back_populates="run",
        cascade="all,delete-orphan",
    )
    artifacts = relationship(
        "LabArtifact",
        back_populates="run",
        cascade="all,delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            f"mode IN ({', '.join(repr(m) for m in LAB_MODES)})",
            name="ck_lab_runs_mode",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in LAB_RUN_STATUSES)})",
            name="ck_lab_runs_status",
        ),
    )


# ---------------------------------------------------------------------------
# 3. lab_node_runs
# ---------------------------------------------------------------------------


class LabNodeRun(Base):
    """Per-node execution row inside a :class:`LabRun`."""

    __tablename__ = "lab_node_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("lab_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(String(120), nullable=False, index=True)
    node_type = Column(String(120), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    output_locator = Column(JSON, nullable=False, default=dict)
    metrics = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    log_label = Column(String(240), nullable=True)

    run = relationship("LabRun", back_populates="node_runs")

    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in LAB_NODE_STATUSES)})",
            name="ck_lab_node_runs_status",
        ),
        UniqueConstraint("run_id", "node_id", name="uq_lab_node_runs_run_node"),
    )


# ---------------------------------------------------------------------------
# 4. lab_artifacts
# ---------------------------------------------------------------------------


class LabArtifact(Base):
    """A file / Arrow table / tearsheet produced by a node."""

    __tablename__ = "lab_artifacts"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("lab_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(String(120), nullable=True, index=True)
    kind = Column(String(64), nullable=False, index=True)
    uri = Column(String(960), nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    schema_json = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    run = relationship("LabRun", back_populates="artifacts")


# ---------------------------------------------------------------------------
# 5. lab_snippets
# ---------------------------------------------------------------------------


class LabSnippet(Base):
    """User-authored Python / SQL snippet (version-locked)."""

    __tablename__ = "lab_snippets"

    id = Column(String(36), primary_key=True, default=_uuid)
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name = Column(String(240), nullable=False)
    language = Column(String(24), nullable=False, default="python")
    source = Column(Text, nullable=False)
    manifest = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=False, index=True)
    ast_safe = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    parent_snippet_id = Column(
        String(36),
        ForeignKey("lab_snippets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    promoted = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"language IN ({', '.join(repr(l) for l in LAB_SNIPPET_LANGS)})",
            name="ck_lab_snippets_language",
        ),
        UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_lab_snippets_workspace_name_version",
        ),
    )


# ---------------------------------------------------------------------------
# 6. lab_labels
# ---------------------------------------------------------------------------


class LabLabel(Base):
    """User-authored chart annotation (support/resistance, trendline, ...)."""

    __tablename__ = "lab_labels"

    id = Column(String(36), primary_key=True, default=_uuid)
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    vt_symbol = Column(String(120), nullable=False, index=True)
    interval = Column(String(24), nullable=False, default="1m")
    t_start = Column(DateTime, nullable=False)
    t_end = Column(DateTime, nullable=True)
    kind = Column(String(40), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    run_id = Column(
        String(36),
        ForeignKey("lab_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"kind IN ({', '.join(repr(k) for k in LAB_LABEL_KINDS)})",
            name="ck_lab_labels_kind",
        ),
    )


Index("ix_lab_labels_lab_symbol", LabLabel.lab_id, LabLabel.vt_symbol)


# ---------------------------------------------------------------------------
# 7. lab_notes
# ---------------------------------------------------------------------------


class LabNote(Base):
    """Markdown note attached to a graph / run / label / paper / snippet."""

    __tablename__ = "lab_notes"

    id = Column(String(36), primary_key=True, default=_uuid)
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_kind = Column(String(24), nullable=False, index=True)
    target_id = Column(String(120), nullable=False, index=True)
    body_md = Column(Text, nullable=False)
    citations = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"target_kind IN ({', '.join(repr(t) for t in LAB_NOTE_TARGETS)})",
            name="ck_lab_notes_target_kind",
        ),
    )


Index("ix_lab_notes_target", LabNote.target_kind, LabNote.target_id)


# ---------------------------------------------------------------------------
# 8. lab_paper_chunks
# ---------------------------------------------------------------------------


class LabPaperChunk(Base):
    """pgvector-indexed paper chunk for the Data Lab hybrid retrieval.

    The canonical paper-chunk surface for agents stays the existing
    :class:`RagChunk` / :class:`RagCorpus` tables (reachable via the
    HierarchicalRAG bridge). This table is a denormalised slice with
    a stable pgvector HNSW index so the Data Lab can run BM25 +
    pgvector + MMR rerank without touching the upstream corpus.
    """

    __tablename__ = "lab_paper_chunks"

    id = Column(String(64), primary_key=True)
    lab_id = Column(
        String(36),
        ForeignKey("labs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rag_chunk_id = Column(String(64), nullable=True, index=True)
    paper_title = Column(String(400), nullable=True)
    source_uri = Column(String(960), nullable=True)
    chunk_ord = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)
    embedding_model = Column(String(120), nullable=True)
    # The raw column type is patched to ``vector(N)`` by migration
    # 0057 on Postgres; on SQLite test environments it stays a JSON
    # ARRAY (queryable for membership but not similarity).
    embedding = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


__all__ = [
    "LAB_LABEL_KINDS",
    "LAB_MODES",
    "LAB_NODE_STATUSES",
    "LAB_NOTE_TARGETS",
    "LAB_RUN_STATUSES",
    "LAB_SNIPPET_LANGS",
    "LabArtifact",
    "LabGraph",
    "LabLabel",
    "LabNodeRun",
    "LabNote",
    "LabPaperChunk",
    "LabRun",
    "LabSnippet",
]
