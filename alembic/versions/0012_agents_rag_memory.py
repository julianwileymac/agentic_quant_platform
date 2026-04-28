"""agents-rag-memory expansion: spec/run/eval + RAG mirror + memory + regulatory

Revision ID: 0012_agents_rag_memory
Revises: 0011_iceberg_catalog_columns
Create Date: 2026-04-27

Single migration that lands the Phase 2 + Phase 3 schema:

- ``agent_specs`` / ``agent_spec_versions`` — declarative agent specs +
  immutable hash-locked versions.
- ``agent_runs_v2`` / ``agent_run_steps`` / ``agent_run_artifacts`` —
  spec-driven runtime persistence with full step trace.
- ``agent_evaluations`` / ``agent_eval_metrics`` — evaluation harness.
- ``agent_annotations`` — user/agent annotations for optimisation.
- ``rag_corpora`` / ``rag_documents`` / ``rag_chunks`` /
  ``rag_summaries`` / ``rag_queries`` / ``rag_eval_runs`` — Postgres
  mirror of the Redis hierarchical RAG state.
- ``memory_episodes`` / ``memory_reflections`` / ``memory_outcomes`` —
  durable memory tables for the agent runtime.
- ``cfpb_complaints`` / ``fda_applications`` / ``fda_adverse_events`` /
  ``fda_recalls`` / ``uspto_patents`` / ``uspto_trademarks`` /
  ``uspto_assignments`` — third-order regulatory ingest tables.

All new tables; nothing existing is modified, so legacy data is
untouched.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_agents_rag_memory"
down_revision = "0011_iceberg_catalog_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ agent specs
    op.create_table(
        "agent_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_specs_name", "agent_specs", ["name"], unique=True)

    op.create_table(
        "agent_spec_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "spec_id",
            sa.String(length=36),
            sa.ForeignKey("agent_specs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_spec_versions_spec_id", "agent_spec_versions", ["spec_id"])
    op.create_index("ix_agent_spec_versions_spec_version", "agent_spec_versions", ["spec_id", "version"])
    op.create_index("ix_agent_spec_versions_hash", "agent_spec_versions", ["spec_hash"], unique=True)

    # ------------------------------------------------------------------ runs
    op.create_table(
        "agent_runs_v2",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_name", sa.String(length=120), nullable=False),
        sa.Column(
            "spec_version_id",
            sa.String(length=36),
            sa.ForeignKey("agent_spec_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("inputs", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("n_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_rag_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_runs_v2_spec_name", "agent_runs_v2", ["spec_name"])
    op.create_index("ix_agent_runs_v2_status", "agent_runs_v2", ["status"])
    op.create_index("ix_agent_runs_v2_task_id", "agent_runs_v2", ["task_id"])
    op.create_index("ix_agent_runs_v2_session_id", "agent_runs_v2", ["session_id"])

    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])
    op.create_index("ix_agent_run_steps_kind", "agent_run_steps", ["kind"])
    op.create_index("ix_agent_run_steps_run_seq", "agent_run_steps", ["run_id", "seq"])

    op.create_table(
        "agent_run_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "step_id",
            sa.String(length=36),
            sa.ForeignKey("agent_run_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("uri", sa.String(length=1024), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_run_artifacts_run_id", "agent_run_artifacts", ["run_id"])

    # ------------------------------------------------------------------ evaluation
    op.create_table(
        "agent_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_name", sa.String(length=120), nullable=False),
        sa.Column("spec_version_id", sa.String(length=36), nullable=True),
        sa.Column("eval_set_name", sa.String(length=240), nullable=False),
        sa.Column("n_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aggregate", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_evaluations_spec_name", "agent_evaluations", ["spec_name"])

    op.create_table(
        "agent_eval_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("agent_evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(length=120), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
    )
    op.create_index("ix_agent_eval_metrics_eval_id", "agent_eval_metrics", ["evaluation_id"])
    op.create_index("ix_agent_eval_metrics_metric", "agent_eval_metrics", ["metric"])

    op.create_table(
        "agent_annotations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_name", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_annotations_spec_name", "agent_annotations", ["spec_name"])
    op.create_index("ix_agent_annotations_label", "agent_annotations", ["label"])
    op.create_index("ix_agent_annotations_vt_symbol", "agent_annotations", ["vt_symbol"])

    # ------------------------------------------------------------------ RAG mirror
    op.create_table(
        "rag_corpora",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("order", sa.String(length=20), nullable=False),
        sa.Column("l1", sa.String(length=80), nullable=False),
        sa.Column("l2", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("iceberg_identifier", sa.String(length=240), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_corpora_name", "rag_corpora", ["name"], unique=True)
    op.create_index("ix_rag_corpora_order", "rag_corpora", ["order"])
    op.create_index("ix_rag_corpora_l1", "rag_corpora", ["l1"])

    op.create_table(
        "rag_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("corpus", sa.String(length=120), nullable=False),
        sa.Column("source_id", sa.String(length=240), nullable=False),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_documents_corpus", "rag_documents", ["corpus"])
    op.create_index("ix_rag_documents_source_id", "rag_documents", ["source_id"])
    op.create_index("ix_rag_documents_vt_symbol", "rag_documents", ["vt_symbol"])

    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("corpus", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("doc_id", sa.String(length=240), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_chunks_corpus", "rag_chunks", ["corpus"])
    op.create_index("ix_rag_chunks_level", "rag_chunks", ["level"])
    op.create_index("ix_rag_chunks_doc_id", "rag_chunks", ["doc_id"])
    op.create_index("ix_rag_chunks_vt_symbol", "rag_chunks", ["vt_symbol"])

    op.create_table(
        "rag_summaries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("corpus", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("raptor_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cluster_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("member_ids", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_summaries_corpus", "rag_summaries", ["corpus"])

    op.create_table(
        "rag_queries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("plan_level", sa.String(length=20), nullable=False, server_default="walk"),
        sa.Column("plan_corpus", sa.String(length=120), nullable=False, server_default="*"),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_queries_created_at", "rag_queries", ["created_at"])

    op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False, server_default="adhoc"),
        sa.Column("level", sa.String(length=8), nullable=False, server_default="l3"),
        sa.Column("k", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("n_queries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("aggregate", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------ memory
    op.create_table(
        "memory_episodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_episodes_role", "memory_episodes", ["role"])
    op.create_index("ix_memory_episodes_vt_symbol", "memory_episodes", ["vt_symbol"])

    op.create_table(
        "memory_reflections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_reflections_role", "memory_reflections", ["role"])
    op.create_index("ix_memory_reflections_lookup", "memory_reflections", ["role", "vt_symbol", "created_at"])

    op.create_table(
        "memory_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("decision_id", sa.String(length=60), nullable=False),
        sa.Column("vt_symbol", sa.String(length=64), nullable=False),
        sa.Column("decision_at", sa.DateTime(), nullable=True),
        sa.Column("outcome_at", sa.DateTime(), nullable=True),
        sa.Column("raw_return", sa.Float(), nullable=True),
        sa.Column("benchmark_return", sa.Float(), nullable=True),
        sa.Column("excess_return", sa.Float(), nullable=True),
        sa.Column("direction_correct", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_outcomes_decision_id", "memory_outcomes", ["decision_id"])
    op.create_index("ix_memory_outcomes_vt_symbol", "memory_outcomes", ["vt_symbol"])

    # ------------------------------------------------------------------ regulatory
    op.create_table(
        "cfpb_complaints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("complaint_id", sa.String(length=40), nullable=False, unique=True),
        sa.Column("company", sa.String(length=240), nullable=False),
        sa.Column("company_response", sa.String(length=120), nullable=True),
        sa.Column("consumer_consent_provided", sa.String(length=40), nullable=True),
        sa.Column("consumer_complaint_narrative", sa.Text(), nullable=True),
        sa.Column("date_received", sa.DateTime(), nullable=True),
        sa.Column("date_sent_to_company", sa.DateTime(), nullable=True),
        sa.Column("issue", sa.String(length=240), nullable=True),
        sa.Column("sub_issue", sa.String(length=240), nullable=True),
        sa.Column("product", sa.String(length=120), nullable=True),
        sa.Column("sub_product", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("zip_code", sa.String(length=16), nullable=True),
        sa.Column("submitted_via", sa.String(length=40), nullable=True),
        sa.Column("tags", sa.String(length=240), nullable=True),
        sa.Column("timely", sa.String(length=8), nullable=True),
        sa.Column("has_narrative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cfpb_complaints_complaint_id", "cfpb_complaints", ["complaint_id"], unique=True)
    op.create_index("ix_cfpb_complaints_company", "cfpb_complaints", ["company"])
    op.create_index("ix_cfpb_complaints_date_received", "cfpb_complaints", ["date_received"])
    op.create_index("ix_cfpb_complaints_issue", "cfpb_complaints", ["issue"])
    op.create_index("ix_cfpb_complaints_product", "cfpb_complaints", ["product"])
    op.create_index("ix_cfpb_complaints_vt_symbol", "cfpb_complaints", ["vt_symbol"])
    op.create_index("ix_cfpb_company_date", "cfpb_complaints", ["company", "date_received"])

    op.create_table(
        "fda_applications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("application_number", sa.String(length=40), nullable=False, unique=True),
        sa.Column("application_type", sa.String(length=20), nullable=True),
        sa.Column("sponsor_name", sa.String(length=240), nullable=False),
        sa.Column("drug_name", sa.String(length=240), nullable=True),
        sa.Column("indication", sa.Text(), nullable=True),
        sa.Column("submission_status", sa.String(length=60), nullable=True),
        sa.Column("submission_date", sa.DateTime(), nullable=True),
        sa.Column("approval_date", sa.DateTime(), nullable=True),
        sa.Column("review_priority", sa.String(length=40), nullable=True),
        sa.Column("therapeutic_area", sa.String(length=120), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fda_applications_application_number", "fda_applications", ["application_number"], unique=True)
    op.create_index("ix_fda_applications_sponsor_name", "fda_applications", ["sponsor_name"])
    op.create_index("ix_fda_applications_drug_name", "fda_applications", ["drug_name"])
    op.create_index("ix_fda_applications_application_type", "fda_applications", ["application_type"])
    op.create_index("ix_fda_applications_submission_date", "fda_applications", ["submission_date"])
    op.create_index("ix_fda_applications_vt_symbol", "fda_applications", ["vt_symbol"])

    op.create_table(
        "fda_adverse_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("report_id", sa.String(length=60), nullable=False, unique=True),
        sa.Column("received_date", sa.DateTime(), nullable=True),
        sa.Column("product_name", sa.String(length=240), nullable=True),
        sa.Column("manufacturer_name", sa.String(length=240), nullable=True),
        sa.Column("reactions", sa.Text(), nullable=True),
        sa.Column("outcomes", sa.Text(), nullable=True),
        sa.Column("is_serious", sa.Boolean(), nullable=True),
        sa.Column("patient_age", sa.Float(), nullable=True),
        sa.Column("patient_sex", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fda_adverse_events_report_id", "fda_adverse_events", ["report_id"], unique=True)
    op.create_index("ix_fda_adverse_events_product", "fda_adverse_events", ["product_name"])
    op.create_index("ix_fda_adverse_events_manufacturer", "fda_adverse_events", ["manufacturer_name"])
    op.create_index("ix_fda_adverse_events_received", "fda_adverse_events", ["received_date"])
    op.create_index("ix_fda_adverse_events_vt_symbol", "fda_adverse_events", ["vt_symbol"])

    op.create_table(
        "fda_recalls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("recall_number", sa.String(length=60), nullable=False, unique=True),
        sa.Column("recalling_firm", sa.String(length=240), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("product_description", sa.Text(), nullable=True),
        sa.Column("reason_for_recall", sa.Text(), nullable=True),
        sa.Column("code_info", sa.Text(), nullable=True),
        sa.Column("distribution_pattern", sa.Text(), nullable=True),
        sa.Column("voluntary_mandated", sa.String(length=60), nullable=True),
        sa.Column("initial_firm_notification", sa.String(length=120), nullable=True),
        sa.Column("recall_initiation_date", sa.DateTime(), nullable=True),
        sa.Column("report_date", sa.DateTime(), nullable=True),
        sa.Column("termination_date", sa.DateTime(), nullable=True),
        sa.Column("product_type", sa.String(length=40), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fda_recalls_recall_number", "fda_recalls", ["recall_number"], unique=True)
    op.create_index("ix_fda_recalls_recalling_firm", "fda_recalls", ["recalling_firm"])
    op.create_index("ix_fda_recalls_classification", "fda_recalls", ["classification"])
    op.create_index("ix_fda_recalls_recall_initiation_date", "fda_recalls", ["recall_initiation_date"])
    op.create_index("ix_fda_recalls_vt_symbol", "fda_recalls", ["vt_symbol"])

    op.create_table(
        "uspto_patents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("patent_number", sa.String(length=40), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("filing_date", sa.DateTime(), nullable=True),
        sa.Column("grant_date", sa.DateTime(), nullable=True),
        sa.Column("assignee", sa.String(length=240), nullable=True),
        sa.Column("inventors", sa.JSON(), nullable=True),
        sa.Column("classification", sa.String(length=120), nullable=True),
        sa.Column("application_number", sa.String(length=60), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_uspto_patents_patent_number", "uspto_patents", ["patent_number"], unique=True)
    op.create_index("ix_uspto_patents_assignee", "uspto_patents", ["assignee"])
    op.create_index("ix_uspto_patents_grant_date", "uspto_patents", ["grant_date"])
    op.create_index("ix_uspto_patents_filing_date", "uspto_patents", ["filing_date"])
    op.create_index("ix_uspto_patents_application_number", "uspto_patents", ["application_number"])
    op.create_index("ix_uspto_patents_vt_symbol", "uspto_patents", ["vt_symbol"])

    op.create_table(
        "uspto_trademarks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("serial_number", sa.String(length=40), nullable=False, unique=True),
        sa.Column("registration_number", sa.String(length=40), nullable=True),
        sa.Column("mark_text", sa.String(length=480), nullable=True),
        sa.Column("owner", sa.String(length=240), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=True),
        sa.Column("filing_date", sa.DateTime(), nullable=True),
        sa.Column("registration_date", sa.DateTime(), nullable=True),
        sa.Column("abandonment_date", sa.DateTime(), nullable=True),
        sa.Column("class_codes", sa.String(length=240), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_uspto_trademarks_serial_number", "uspto_trademarks", ["serial_number"], unique=True)
    op.create_index("ix_uspto_trademarks_registration_number", "uspto_trademarks", ["registration_number"])
    op.create_index("ix_uspto_trademarks_owner", "uspto_trademarks", ["owner"])
    op.create_index("ix_uspto_trademarks_status", "uspto_trademarks", ["status"])
    op.create_index("ix_uspto_trademarks_filing_date", "uspto_trademarks", ["filing_date"])
    op.create_index("ix_uspto_trademarks_vt_symbol", "uspto_trademarks", ["vt_symbol"])

    op.create_table(
        "uspto_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("assignment_id", sa.String(length=60), nullable=False, unique=True),
        sa.Column("recorded_date", sa.DateTime(), nullable=True),
        sa.Column("execution_date", sa.DateTime(), nullable=True),
        sa.Column("conveyance_text", sa.String(length=240), nullable=True),
        sa.Column("assignor", sa.String(length=240), nullable=True),
        sa.Column("assignee", sa.String(length=240), nullable=True),
        sa.Column("patents", sa.Text(), nullable=True),
        sa.Column("vt_symbol", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_uspto_assignments_assignment_id", "uspto_assignments", ["assignment_id"], unique=True)
    op.create_index("ix_uspto_assignments_assignor", "uspto_assignments", ["assignor"])
    op.create_index("ix_uspto_assignments_assignee", "uspto_assignments", ["assignee"])
    op.create_index("ix_uspto_assignments_recorded_date", "uspto_assignments", ["recorded_date"])
    op.create_index("ix_uspto_assignments_vt_symbol", "uspto_assignments", ["vt_symbol"])


def downgrade() -> None:
    for tbl in (
        "uspto_assignments",
        "uspto_trademarks",
        "uspto_patents",
        "fda_recalls",
        "fda_adverse_events",
        "fda_applications",
        "cfpb_complaints",
        "memory_outcomes",
        "memory_reflections",
        "memory_episodes",
        "rag_eval_runs",
        "rag_queries",
        "rag_summaries",
        "rag_chunks",
        "rag_documents",
        "rag_corpora",
        "agent_annotations",
        "agent_eval_metrics",
        "agent_evaluations",
        "agent_run_artifacts",
        "agent_run_steps",
        "agent_runs_v2",
        "agent_spec_versions",
        "agent_specs",
    ):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
