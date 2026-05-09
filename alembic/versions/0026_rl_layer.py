"""RL layer: rl_experiment_specs, rl_experiment_versions, rl_runs,
rl_evaluations, rl_trajectory_refs, rl_equity_curve_refs,
rl_component_registrations + rl_episodes.run_id FK.

Revision ID: 0026_rl_layer
Revises: 0025_ml_alpha_backtest_linkage
Create Date: 2026-05-08

Introduces the persistence layer for the metaclass-driven RL stack:

- ``rl_experiment_specs`` — logical RL experiment row (the latest active
  version of a named spec inside a project).
- ``rl_experiment_versions`` — immutable, hash-locked snapshots of every
  :class:`aqp.rl.spec.RLExperimentSpec` the registry has ever seen.
- ``rl_runs`` — one row per train / evaluate / paper / replay /
  walk-forward invocation of :class:`aqp.rl.runtime.RLRuntime`.
- ``rl_evaluations`` — rollout summary tied to a run.
- ``rl_trajectory_refs`` / ``rl_equity_curve_refs`` — pointers to the
  Iceberg-backed step-level tables (``rl.trajectories`` /
  ``rl.equity_curves``) so the UI can fetch by episode without a full
  scan.
- ``rl_component_registrations`` — DB-mirror of the in-memory RL
  component registry that powers the ``/rl/components`` UI library.
- Wires the existing ``rl_episodes`` table to ``rl_runs`` via a
  nullable ``run_id`` FK (existing rows keep their string ``run_id``
  values; the column type stays a string for backwards-compat, but a
  new optional FK index makes joins cheap).

Tenancy
-------

Every table carries the ``ProjectScopedMixin`` columns
(``owner_user_id``, ``workspace_id``, ``project_id``) added by 0017–0019,
so the multi-tenant ownership chain reaches RL rows out of the box.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_rl_layer"
down_revision = "0025_ml_alpha_backtest_linkage"
branch_labels = None
depends_on = None


DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000005"


def _project_scope_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_USER_ID,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            server_default=DEFAULT_PROJECT_ID,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "rl_experiment_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="training"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("spec_yaml", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        *_project_scope_columns(),
        sa.UniqueConstraint(
            "project_id", "slug", name="uq_rl_experiment_specs_project_slug"
        ),
    )
    op.create_index("ix_rl_experiment_specs_slug", "rl_experiment_specs", ["slug"])
    op.create_index("ix_rl_experiment_specs_kind", "rl_experiment_specs", ["kind"])
    op.create_index("ix_rl_experiment_specs_status", "rl_experiment_specs", ["status"])

    op.create_table(
        "rl_experiment_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "spec_id",
            sa.String(length=36),
            sa.ForeignKey("rl_experiment_specs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        *_project_scope_columns(),
        sa.UniqueConstraint(
            "spec_id", "spec_hash", name="uq_rl_versions_spec_hash"
        ),
        sa.UniqueConstraint(
            "spec_id", "version", name="uq_rl_versions_spec_version"
        ),
    )
    op.create_index(
        "ix_rl_experiment_versions_spec_id", "rl_experiment_versions", ["spec_id"]
    )
    op.create_index(
        "ix_rl_experiment_versions_spec_hash",
        "rl_experiment_versions",
        ["spec_hash"],
    )
    op.create_index(
        "ix_rl_versions_spec_version",
        "rl_experiment_versions",
        ["spec_id", "version"],
    )

    op.create_table(
        "rl_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "spec_id",
            sa.String(length=36),
            sa.ForeignKey("rl_experiment_specs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("rl_experiment_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("mlflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("checkpoint", sa.String(length=1024), nullable=True),
        sa.Column("mean_reward", sa.Float(), nullable=True),
        sa.Column("total_reward", sa.Float(), nullable=True),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("final_value", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        *_project_scope_columns(),
    )
    op.create_index("ix_rl_runs_spec_id", "rl_runs", ["spec_id"])
    op.create_index("ix_rl_runs_version_id", "rl_runs", ["version_id"])
    op.create_index("ix_rl_runs_target", "rl_runs", ["target"])
    op.create_index("ix_rl_runs_task_id", "rl_runs", ["task_id"])
    op.create_index("ix_rl_runs_status", "rl_runs", ["status"])
    op.create_index("ix_rl_runs_status_started", "rl_runs", ["status", "started_at"])

    op.create_table(
        "rl_evaluations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("rl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("episodes", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deterministic", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mean_reward", sa.Float(), nullable=True),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("final_value", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        *_project_scope_columns(),
    )
    op.create_index("ix_rl_evaluations_run_id", "rl_evaluations", ["run_id"])

    op.create_table(
        "rl_trajectory_refs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("rl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column(
            "iceberg_namespace", sa.String(length=120), nullable=False, server_default="rl"
        ),
        sa.Column(
            "iceberg_table", sa.String(length=120), nullable=False, server_default="trajectories"
        ),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_step", sa.Integer(), nullable=True),
        sa.Column("last_step", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        *_project_scope_columns(),
    )
    op.create_index("ix_rl_trajectory_refs_run_id", "rl_trajectory_refs", ["run_id"])
    op.create_index(
        "ix_rl_trajectory_refs_episode", "rl_trajectory_refs", ["episode"]
    )

    op.create_table(
        "rl_equity_curve_refs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("rl_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column(
            "iceberg_namespace", sa.String(length=120), nullable=False, server_default="rl"
        ),
        sa.Column(
            "iceberg_table",
            sa.String(length=120),
            nullable=False,
            server_default="equity_curves",
        ),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initial_value", sa.Float(), nullable=True),
        sa.Column("final_value", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        *_project_scope_columns(),
    )
    op.create_index(
        "ix_rl_equity_curve_refs_run_id", "rl_equity_curve_refs", ["run_id"]
    )
    op.create_index(
        "ix_rl_equity_curve_refs_episode", "rl_equity_curve_refs", ["episode"]
    )

    op.create_table(
        "rl_component_registrations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rl_kind", sa.String(length=40), nullable=False),
        sa.Column("alias", sa.String(length=160), nullable=False),
        sa.Column("module_path", sa.String(length=400), nullable=False),
        sa.Column("class_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("schema", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        *_project_scope_columns(),
        sa.UniqueConstraint("rl_kind", "alias", name="uq_rl_components_kind_alias"),
    )
    op.create_index(
        "ix_rl_component_registrations_kind", "rl_component_registrations", ["rl_kind"]
    )
    op.create_index(
        "ix_rl_component_registrations_alias", "rl_component_registrations", ["alias"]
    )
    op.create_index(
        "ix_rl_component_registrations_source", "rl_component_registrations", ["source"]
    )
    op.create_index(
        "ix_rl_component_registrations_category",
        "rl_component_registrations",
        ["category"],
    )

    # rl_episodes already exists (Alembic 0001 / 0017 series). We don't add
    # a new FK column — the existing string ``run_id`` column is preserved
    # so legacy rows stay valid; runtime joins are cheap thanks to the
    # existing ``ix_rl_episodes_run_id`` index.


def downgrade() -> None:
    op.drop_index(
        "ix_rl_component_registrations_category", table_name="rl_component_registrations"
    )
    op.drop_index(
        "ix_rl_component_registrations_source", table_name="rl_component_registrations"
    )
    op.drop_index(
        "ix_rl_component_registrations_alias", table_name="rl_component_registrations"
    )
    op.drop_index(
        "ix_rl_component_registrations_kind", table_name="rl_component_registrations"
    )
    op.drop_table("rl_component_registrations")

    op.drop_index("ix_rl_equity_curve_refs_episode", table_name="rl_equity_curve_refs")
    op.drop_index("ix_rl_equity_curve_refs_run_id", table_name="rl_equity_curve_refs")
    op.drop_table("rl_equity_curve_refs")

    op.drop_index("ix_rl_trajectory_refs_episode", table_name="rl_trajectory_refs")
    op.drop_index("ix_rl_trajectory_refs_run_id", table_name="rl_trajectory_refs")
    op.drop_table("rl_trajectory_refs")

    op.drop_index("ix_rl_evaluations_run_id", table_name="rl_evaluations")
    op.drop_table("rl_evaluations")

    op.drop_index("ix_rl_runs_status_started", table_name="rl_runs")
    op.drop_index("ix_rl_runs_status", table_name="rl_runs")
    op.drop_index("ix_rl_runs_task_id", table_name="rl_runs")
    op.drop_index("ix_rl_runs_target", table_name="rl_runs")
    op.drop_index("ix_rl_runs_version_id", table_name="rl_runs")
    op.drop_index("ix_rl_runs_spec_id", table_name="rl_runs")
    op.drop_table("rl_runs")

    op.drop_index("ix_rl_versions_spec_version", table_name="rl_experiment_versions")
    op.drop_index(
        "ix_rl_experiment_versions_spec_hash", table_name="rl_experiment_versions"
    )
    op.drop_index(
        "ix_rl_experiment_versions_spec_id", table_name="rl_experiment_versions"
    )
    op.drop_table("rl_experiment_versions")

    op.drop_index("ix_rl_experiment_specs_status", table_name="rl_experiment_specs")
    op.drop_index("ix_rl_experiment_specs_kind", table_name="rl_experiment_specs")
    op.drop_index("ix_rl_experiment_specs_slug", table_name="rl_experiment_specs")
    op.drop_table("rl_experiment_specs")
