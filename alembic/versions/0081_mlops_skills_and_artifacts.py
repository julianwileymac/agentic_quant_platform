"""MLOps initial slice — skills, compiled artifacts, cache, serving, OOD audit.

Revision ID: 0081_mlops_skills_and_artifacts
Revises: 0080_team_airbyte_workspaces
Create Date: 2026-05-25

Tables created (all project-scoped, mirroring the existing
``aqp/persistence/_tenancy_mixins.py::ProjectScopedMixin``):

- ``ml_skills`` + ``ml_skill_versions`` — hash-locked snapshots of
  :class:`aqp_models.spec.MLSkillSpec` (mirrors ``agent_spec_versions``
  per AGENTS rule 13/15/17/24/41).
- ``ml_skill_runs`` — run ledger for :class:`MLSkillRuntime`. Carries
  ``experiment_id`` + ``test_id`` FKs per AGENTS rule 34.
- ``ml_compiled_artifacts`` — ONNX / TensorRT / TorchScript /
  quantised binaries with SHA-256 provenance.
- ``ml_cache_entries`` — LRU state mirror so the operator UI can show
  active cache entries across workers.
- ``ml_serving_sessions`` — active continuous-batching sessions +
  halt state.
- ``ml_ood_violations`` — append-only audit of rejected OOD checks.

Per AGENTS rule 6 this migration is immutable once shipped — bugs
land in follow-up migrations.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0081_mlops_skills_and_artifacts"
down_revision = "0080_team_airbyte_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_skills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("kind", sa.String(64), nullable=False, server_default="custom"),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("annotations", sa.JSON, nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ml_skills_name", "ml_skills", ["name"], unique=True)
    op.create_index("ix_ml_skills_workspace_id", "ml_skills", ["workspace_id"])

    op.create_table(
        "ml_skill_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "skill_id",
            sa.String(36),
            sa.ForeignKey("ml_skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("skill_id", "version", name="uq_ml_skill_versions_skill_version"),
        sa.UniqueConstraint("spec_hash", name="uq_ml_skill_versions_spec_hash"),
    )
    op.create_index("ix_ml_skill_versions_skill_id", "ml_skill_versions", ["skill_id"])

    op.create_table(
        "ml_skill_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_name", sa.String(120), nullable=False),
        sa.Column("skill_spec_version_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("elapsed_ms", sa.Float, nullable=True),
        sa.Column("step_outputs", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("actor", sa.String(120), nullable=True),
        sa.Column("actor_kind", sa.String(32), nullable=True),
        sa.Column(
            "experiment_id",
            sa.String(36),
            sa.ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "test_id",
            sa.String(36),
            sa.ForeignKey("aqp_tests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_ml_skill_runs_skill_name", "ml_skill_runs", ["skill_name"])
    op.create_index("ix_ml_skill_runs_status", "ml_skill_runs", ["status"])
    op.create_index("ix_ml_skill_runs_workspace_id", "ml_skill_runs", ["workspace_id"])
    op.create_index("ix_ml_skill_runs_experiment_id", "ml_skill_runs", ["experiment_id"])

    op.create_table(
        "ml_compiled_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "base_model_version_id",
            sa.String(36),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("artifact_format", sa.String(32), nullable=False),
        sa.Column("artifact_path", sa.String(512), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("compile_kwargs", sa.JSON, nullable=True),
        sa.Column("elapsed_ms", sa.Float, nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ml_compiled_artifacts_base_model_version_id",
        "ml_compiled_artifacts",
        ["base_model_version_id"],
    )
    op.create_index("ix_ml_compiled_artifacts_target", "ml_compiled_artifacts", ["target"])
    op.create_index(
        "ix_ml_compiled_artifacts_sha256",
        "ml_compiled_artifacts",
        ["artifact_sha256"],
    )

    op.create_table(
        "ml_cache_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False, unique=True),
        sa.Column("model_class", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("hits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_access", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("evicted_at", sa.DateTime, nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ml_cache_entries_key", "ml_cache_entries", ["key"], unique=True)
    op.create_index("ix_ml_cache_entries_workspace_id", "ml_cache_entries", ["workspace_id"])

    op.create_table(
        "ml_serving_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False, unique=True),
        sa.Column("model_alias", sa.String(120), nullable=False),
        sa.Column("model_class", sa.String(120), nullable=False),
        sa.Column("max_batch_size", sa.Integer, nullable=False, server_default="64"),
        sa.Column("max_wait_ms", sa.Integer, nullable=False, server_default="25"),
        sa.Column("halted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ml_serving_sessions_session_id",
        "ml_serving_sessions",
        ["session_id"],
        unique=True,
    )
    op.create_index("ix_ml_serving_sessions_halted", "ml_serving_sessions", ["halted"])
    op.create_index(
        "ix_ml_serving_sessions_workspace_id", "ml_serving_sessions", ["workspace_id"]
    )

    op.create_table(
        "ml_ood_violations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_name", sa.String(120), nullable=False),
        sa.Column("skill_step", sa.String(120), nullable=True),
        sa.Column("reason", sa.String(240), nullable=True),
        sa.Column("failures_in_window", sa.Integer, nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_ml_ood_violations_rule_name", "ml_ood_violations", ["rule_name"])
    op.create_index(
        "ix_ml_ood_violations_workspace_id", "ml_ood_violations", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ml_ood_violations_workspace_id", table_name="ml_ood_violations")
    op.drop_index("ix_ml_ood_violations_rule_name", table_name="ml_ood_violations")
    op.drop_table("ml_ood_violations")

    op.drop_index(
        "ix_ml_serving_sessions_workspace_id", table_name="ml_serving_sessions"
    )
    op.drop_index("ix_ml_serving_sessions_halted", table_name="ml_serving_sessions")
    op.drop_index("ix_ml_serving_sessions_session_id", table_name="ml_serving_sessions")
    op.drop_table("ml_serving_sessions")

    op.drop_index("ix_ml_cache_entries_workspace_id", table_name="ml_cache_entries")
    op.drop_index("ix_ml_cache_entries_key", table_name="ml_cache_entries")
    op.drop_table("ml_cache_entries")

    op.drop_index(
        "ix_ml_compiled_artifacts_sha256", table_name="ml_compiled_artifacts"
    )
    op.drop_index(
        "ix_ml_compiled_artifacts_target", table_name="ml_compiled_artifacts"
    )
    op.drop_index(
        "ix_ml_compiled_artifacts_base_model_version_id",
        table_name="ml_compiled_artifacts",
    )
    op.drop_table("ml_compiled_artifacts")

    op.drop_index("ix_ml_skill_runs_experiment_id", table_name="ml_skill_runs")
    op.drop_index("ix_ml_skill_runs_workspace_id", table_name="ml_skill_runs")
    op.drop_index("ix_ml_skill_runs_status", table_name="ml_skill_runs")
    op.drop_index("ix_ml_skill_runs_skill_name", table_name="ml_skill_runs")
    op.drop_table("ml_skill_runs")

    op.drop_index("ix_ml_skill_versions_skill_id", table_name="ml_skill_versions")
    op.drop_table("ml_skill_versions")

    op.drop_index("ix_ml_skills_workspace_id", table_name="ml_skills")
    op.drop_index("ix_ml_skills_name", table_name="ml_skills")
    op.drop_table("ml_skills")
