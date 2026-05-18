"""Terraform IaC control plane + multi-tenant Entra ID link.

Revision ID: 0050_terraform_iac_plus_entra
Revises: 0049_paper_baseline_aspects
Create Date: 2026-05-17

Adds the 5th sibling spec-runtime (Terraform) ledger + spec versioning
tables plus the multi-tenant Entra ID -> Organization index:

- ``terraform_providers`` (per-tenant provider connection profile)
- ``terraform_stack_specs`` (logical stack, latest active version)
- ``terraform_stack_spec_versions`` (immutable, hash-locked snapshots)
- ``terraform_workspaces`` (one row per stack x environment x tenant)
- ``terraform_runs`` (per-execution ledger row + experiment_id +
  test_id FKs per AGENTS rule 34)
- ``terraform_state_versions`` (snapshot after every successful apply)
- ``terraform_policy_attachments`` (OPA / Sentinel binding)
- ``entra_tenant_links`` (Entra ``tid`` -> Organization mapping)

The migration is strictly additive — existing tables are untouched.
Downgrade returns the database to ``0049_paper_baseline_aspects``.

AGENTS rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0050_terraform_iac_plus_entra"
down_revision = "0049_paper_baseline_aspects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # entra_tenant_links — multi-tenant Entra ID -> Organization
    # ------------------------------------------------------------------
    op.create_table(
        "entra_tenant_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("entra_tenant_id", sa.String(length=80), nullable=False),
        sa.Column("primary_domain", sa.String(length=240), nullable=True),
        sa.Column("display_name", sa.String(length=240), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("allowed_email_domains", sa.Text(), nullable=True),
        sa.Column("role_mapping", sa.JSON(), nullable=True),
        sa.Column("requested_by_email", sa.String(length=320), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "entra_tenant_id", name="uq_entra_tenant_links_tid"
        ),
    )
    op.create_index(
        "ix_entra_tenant_links_organization_id",
        "entra_tenant_links",
        ["organization_id"],
    )
    op.create_index(
        "ix_entra_tenant_links_entra_tenant_id",
        "entra_tenant_links",
        ["entra_tenant_id"],
    )
    op.create_index(
        "ix_entra_tenant_links_primary_domain",
        "entra_tenant_links",
        ["primary_domain"],
    )
    op.create_index(
        "ix_entra_tenant_links_status",
        "entra_tenant_links",
        ["status"],
    )
    op.create_index(
        "ix_entra_tenant_links_org_status",
        "entra_tenant_links",
        ["organization_id", "status"],
    )

    # ------------------------------------------------------------------
    # terraform_providers
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_providers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("default_region", sa.String(length=64), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("credential_key", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # TenantOwnedMixin columns.
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint(
            "workspace_id", "slug", name="uq_terraform_providers_workspace_slug"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_providers_slug", "terraform_providers", ["slug"]
    )
    op.create_index(
        "ix_terraform_providers_kind", "terraform_providers", ["kind"]
    )
    op.create_index(
        "ix_terraform_providers_status", "terraform_providers", ["status"]
    )
    op.create_index(
        "ix_terraform_providers_owner_user_id",
        "terraform_providers",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_terraform_providers_workspace_id",
        "terraform_providers",
        ["workspace_id"],
    )
    op.create_index(
        "ix_terraform_providers_kind_status",
        "terraform_providers",
        ["kind", "status"],
    )

    # ------------------------------------------------------------------
    # terraform_stack_specs + terraform_stack_spec_versions
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_stack_specs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("module_kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "current_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # ProjectScopedMixin columns.
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint(
            "project_id", "slug", name="uq_terraform_stack_specs_project_slug"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_stack_specs_slug", "terraform_stack_specs", ["slug"]
    )
    op.create_index(
        "ix_terraform_stack_specs_module_kind",
        "terraform_stack_specs",
        ["module_kind"],
    )
    op.create_index(
        "ix_terraform_stack_specs_project_id",
        "terraform_stack_specs",
        ["project_id"],
    )
    op.create_index(
        "ix_terraform_stack_specs_workspace_id",
        "terraform_stack_specs",
        ["workspace_id"],
    )

    op.create_table(
        "terraform_stack_spec_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("spec_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hcl", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint(
            "spec_hash", name="uq_terraform_stack_spec_versions_hash"
        ),
        sa.ForeignKeyConstraint(
            ["spec_id"],
            ["terraform_stack_specs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_stack_spec_versions_spec_id",
        "terraform_stack_spec_versions",
        ["spec_id"],
    )
    op.create_index(
        "ix_terraform_stack_spec_versions_spec_hash",
        "terraform_stack_spec_versions",
        ["spec_hash"],
    )
    op.create_index(
        "ix_terraform_stack_spec_versions_spec_version",
        "terraform_stack_spec_versions",
        ["spec_id", "version"],
    )

    # ------------------------------------------------------------------
    # terraform_workspaces
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("stack_spec_id", sa.String(length=36), nullable=True),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column(
            "environment",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
        sa.Column(
            "state_backend",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
        sa.Column("state_uri", sa.String(length=1024), nullable=True),
        sa.Column("hcp_workspace_id", sa.String(length=120), nullable=True),
        sa.Column("tenant_org_id", sa.String(length=36), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint(
            "project_id",
            "slug",
            name="uq_terraform_workspaces_project_slug",
        ),
        sa.ForeignKeyConstraint(
            ["stack_spec_id"],
            ["terraform_stack_specs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["terraform_providers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_org_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["aqp_experiments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_workspaces_slug", "terraform_workspaces", ["slug"]
    )
    op.create_index(
        "ix_terraform_workspaces_stack_spec_id",
        "terraform_workspaces",
        ["stack_spec_id"],
    )
    op.create_index(
        "ix_terraform_workspaces_provider_id",
        "terraform_workspaces",
        ["provider_id"],
    )
    op.create_index(
        "ix_terraform_workspaces_environment",
        "terraform_workspaces",
        ["environment"],
    )
    op.create_index(
        "ix_terraform_workspaces_tenant_org_id",
        "terraform_workspaces",
        ["tenant_org_id"],
    )
    op.create_index(
        "ix_terraform_workspaces_archived",
        "terraform_workspaces",
        ["archived"],
    )
    op.create_index(
        "ix_terraform_workspaces_hcp_workspace_id",
        "terraform_workspaces",
        ["hcp_workspace_id"],
    )
    op.create_index(
        "ix_terraform_workspaces_env_archived",
        "terraform_workspaces",
        ["environment", "archived"],
    )
    op.create_index(
        "ix_terraform_workspaces_experiment_id",
        "terraform_workspaces",
        ["experiment_id"],
    )

    # ------------------------------------------------------------------
    # terraform_runs
    # FK to terraform_workspaces is ``terraform_workspace_id`` so it
    # does not collide with the tenancy ``workspace_id`` emitted by
    # ProjectScopedMixin.
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("terraform_workspace_id", sa.String(length=36), nullable=False),
        sa.Column("spec_version_id", sa.String(length=36), nullable=True),
        sa.Column("run_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("started_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("plan_artifact_uri", sa.String(length=1024), nullable=True),
        sa.Column("plan_summary_json", sa.JSON(), nullable=True),
        sa.Column("apply_artifact_uri", sa.String(length=1024), nullable=True),
        sa.Column("stdout_log_uri", sa.String(length=1024), nullable=True),
        sa.Column("stderr_log_uri", sa.String(length=1024), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("lock_id", sa.String(length=120), nullable=True),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("celery_task_id", sa.String(length=120), nullable=True),
        sa.Column("policy_check_result", sa.JSON(), nullable=True),
        sa.Column(
            "halted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("experiment_id", sa.String(length=36), nullable=True),
        sa.Column("test_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["terraform_workspace_id"],
            ["terraform_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["spec_version_id"],
            ["terraform_stack_spec_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"],
            ["terraform_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["aqp_experiments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["test_id"],
            ["aqp_tests.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_runs_terraform_workspace_id",
        "terraform_runs",
        ["terraform_workspace_id"],
    )
    op.create_index(
        "ix_terraform_runs_spec_version_id",
        "terraform_runs",
        ["spec_version_id"],
    )
    op.create_index(
        "ix_terraform_runs_run_kind", "terraform_runs", ["run_kind"]
    )
    op.create_index(
        "ix_terraform_runs_status", "terraform_runs", ["status"]
    )
    op.create_index(
        "ix_terraform_runs_started_by_user_id",
        "terraform_runs",
        ["started_by_user_id"],
    )
    op.create_index(
        "ix_terraform_runs_celery_task_id",
        "terraform_runs",
        ["celery_task_id"],
    )
    op.create_index(
        "ix_terraform_runs_parent_run_id",
        "terraform_runs",
        ["parent_run_id"],
    )
    op.create_index(
        "ix_terraform_runs_halted", "terraform_runs", ["halted"]
    )
    op.create_index(
        "ix_terraform_runs_experiment_id",
        "terraform_runs",
        ["experiment_id"],
    )
    op.create_index(
        "ix_terraform_runs_test_id", "terraform_runs", ["test_id"]
    )
    op.create_index(
        "ix_terraform_runs_status_started",
        "terraform_runs",
        ["status", "started_at"],
    )
    op.create_index(
        "ix_terraform_runs_workspace_kind",
        "terraform_runs",
        ["terraform_workspace_id", "run_kind"],
    )

    # ------------------------------------------------------------------
    # terraform_state_versions
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_state_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("terraform_workspace_id", sa.String(length=36), nullable=False),
        sa.Column("serial", sa.Integer(), nullable=False),
        sa.Column("lineage", sa.String(length=64), nullable=True),
        sa.Column("state_json_uri", sa.String(length=1024), nullable=False),
        sa.Column("state_size_bytes", sa.Integer(), nullable=True),
        sa.Column("outputs_redacted", sa.JSON(), nullable=True),
        sa.Column("resource_count", sa.Integer(), nullable=True),
        sa.Column("created_by_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.UniqueConstraint(
            "terraform_workspace_id",
            "serial",
            name="uq_terraform_state_workspace_serial",
        ),
        sa.ForeignKeyConstraint(
            ["terraform_workspace_id"],
            ["terraform_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_run_id"],
            ["terraform_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_state_versions_terraform_workspace_id",
        "terraform_state_versions",
        ["terraform_workspace_id"],
    )
    op.create_index(
        "ix_terraform_state_versions_created_by_run_id",
        "terraform_state_versions",
        ["created_by_run_id"],
    )

    # ------------------------------------------------------------------
    # terraform_policy_attachments
    # ------------------------------------------------------------------
    op.create_table(
        "terraform_policy_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("terraform_workspace_id", sa.String(length=36), nullable=False),
        sa.Column("policy_set_uri", sa.String(length=1024), nullable=False),
        sa.Column(
            "policy_engine",
            sa.String(length=32),
            nullable=False,
            server_default="opa",
        ),
        sa.Column(
            "hard_mandatory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_check_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_check_passed", sa.Boolean(), nullable=True),
        sa.Column("last_check_at", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["terraform_workspace_id"],
            ["terraform_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_check_run_id"],
            ["terraform_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_terraform_policy_attachments_terraform_workspace_id",
        "terraform_policy_attachments",
        ["terraform_workspace_id"],
    )
    op.create_index(
        "ix_terraform_policy_attachments_policy_engine",
        "terraform_policy_attachments",
        ["policy_engine"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_terraform_policy_attachments_policy_engine",
        table_name="terraform_policy_attachments",
    )
    op.drop_index(
        "ix_terraform_policy_attachments_terraform_workspace_id",
        table_name="terraform_policy_attachments",
    )
    op.drop_table("terraform_policy_attachments")

    op.drop_index(
        "ix_terraform_state_versions_created_by_run_id",
        table_name="terraform_state_versions",
    )
    op.drop_index(
        "ix_terraform_state_versions_terraform_workspace_id",
        table_name="terraform_state_versions",
    )
    op.drop_table("terraform_state_versions")

    for ix in (
        "ix_terraform_runs_workspace_kind",
        "ix_terraform_runs_status_started",
        "ix_terraform_runs_test_id",
        "ix_terraform_runs_experiment_id",
        "ix_terraform_runs_halted",
        "ix_terraform_runs_parent_run_id",
        "ix_terraform_runs_celery_task_id",
        "ix_terraform_runs_started_by_user_id",
        "ix_terraform_runs_status",
        "ix_terraform_runs_run_kind",
        "ix_terraform_runs_spec_version_id",
        "ix_terraform_runs_terraform_workspace_id",
    ):
        op.drop_index(ix, table_name="terraform_runs")
    op.drop_table("terraform_runs")

    for ix in (
        "ix_terraform_workspaces_experiment_id",
        "ix_terraform_workspaces_env_archived",
        "ix_terraform_workspaces_hcp_workspace_id",
        "ix_terraform_workspaces_archived",
        "ix_terraform_workspaces_tenant_org_id",
        "ix_terraform_workspaces_environment",
        "ix_terraform_workspaces_provider_id",
        "ix_terraform_workspaces_stack_spec_id",
        "ix_terraform_workspaces_slug",
    ):
        op.drop_index(ix, table_name="terraform_workspaces")
    op.drop_table("terraform_workspaces")

    for ix in (
        "ix_terraform_stack_spec_versions_spec_version",
        "ix_terraform_stack_spec_versions_spec_hash",
        "ix_terraform_stack_spec_versions_spec_id",
    ):
        op.drop_index(ix, table_name="terraform_stack_spec_versions")
    op.drop_table("terraform_stack_spec_versions")

    for ix in (
        "ix_terraform_stack_specs_workspace_id",
        "ix_terraform_stack_specs_project_id",
        "ix_terraform_stack_specs_module_kind",
        "ix_terraform_stack_specs_slug",
    ):
        op.drop_index(ix, table_name="terraform_stack_specs")
    op.drop_table("terraform_stack_specs")

    for ix in (
        "ix_terraform_providers_kind_status",
        "ix_terraform_providers_workspace_id",
        "ix_terraform_providers_owner_user_id",
        "ix_terraform_providers_status",
        "ix_terraform_providers_kind",
        "ix_terraform_providers_slug",
    ):
        op.drop_index(ix, table_name="terraform_providers")
    op.drop_table("terraform_providers")

    for ix in (
        "ix_entra_tenant_links_org_status",
        "ix_entra_tenant_links_status",
        "ix_entra_tenant_links_primary_domain",
        "ix_entra_tenant_links_entra_tenant_id",
        "ix_entra_tenant_links_organization_id",
    ):
        op.drop_index(ix, table_name="entra_tenant_links")
    op.drop_table("entra_tenant_links")
