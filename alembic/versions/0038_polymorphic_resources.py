"""Polymorphic Resource registry + resource_relations edges.

Revision ID: 0038_polymorphic_resources
Revises: 0037_experiment_test_linkage
Create Date: 2026-05-16

Adds two new tables that back :mod:`aqp.persistence.models_resources`:

- ``resources`` — every content asset with a polymorphic owner
  (organization / team / workspace / project / user).
- ``resource_relations`` — typed edges (``derived_from``, ``uses``,
  ``clones``, ``translated_from``, ``references``).

The Phase 7 LEAN ingester lands strategy templates here; the Phase 2
Neo4j projector mirrors both tables into the ownership graph for fast
multi-hop traversal.

AGENTS.md rule 33 (added in this rollout): All ownership / membership
queries that traverse more than one hop MUST go through
:class:`aqp.graph.OwnershipGraphStore`. Don't hand-write joins over
``organizations / teams / users / memberships / resources``.

AGENTS.md rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0038_polymorphic_resources"
down_revision = "0037_experiment_test_linkage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aqp_resources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("resource_type", sa.String(length=48), nullable=False),
        sa.Column("uri", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_scope_kind", sa.String(length=24), nullable=False),
        sa.Column("owner_scope_id", sa.String(length=36), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("data_payload", sa.LargeBinary(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column(
            "visibility",
            sa.String(length=24),
            nullable=False,
            server_default="private",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # ProjectScopedMixin
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_scope_kind",
            "owner_scope_id",
            "resource_type",
            "slug",
            name="uq_aqp_resources_owner_type_slug",
        ),
    )
    op.create_index("ix_aqp_resources_slug", "aqp_resources", ["slug"])
    op.create_index("ix_aqp_resources_resource_type", "aqp_resources", ["resource_type"])
    op.create_index("ix_aqp_resources_uri", "aqp_resources", ["uri"])
    op.create_index("ix_aqp_resources_owner_scope_kind", "aqp_resources", ["owner_scope_kind"])
    op.create_index("ix_aqp_resources_owner_scope_id", "aqp_resources", ["owner_scope_id"])
    op.create_index("ix_aqp_resources_visibility", "aqp_resources", ["visibility"])
    op.create_index("ix_aqp_resources_owner_user_id", "aqp_resources", ["owner_user_id"])
    op.create_index("ix_aqp_resources_workspace_id", "aqp_resources", ["workspace_id"])
    op.create_index("ix_aqp_resources_project_id", "aqp_resources", ["project_id"])
    op.create_index(
        "ix_aqp_resources_owner_type",
        "aqp_resources",
        ["owner_scope_kind", "owner_scope_id", "resource_type"],
    )
    op.create_index(
        "ix_aqp_resources_workspace_type",
        "aqp_resources",
        ["workspace_id", "resource_type"],
    )

    op.create_table(
        "aqp_resource_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("from_id", sa.String(length=36), nullable=False),
        sa.Column("to_id", sa.String(length=36), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_id", "to_id", "relation", name="uq_aqp_resource_relations_edge"
        ),
    )
    op.create_index("ix_aqp_resource_relations_from_id", "aqp_resource_relations", ["from_id"])
    op.create_index("ix_aqp_resource_relations_to_id", "aqp_resource_relations", ["to_id"])
    op.create_index("ix_aqp_resource_relations_relation", "aqp_resource_relations", ["relation"])
    op.create_index(
        "ix_aqp_resource_relations_to_relation",
        "aqp_resource_relations",
        ["to_id", "relation"],
    )


def downgrade() -> None:
    op.drop_index("ix_aqp_resource_relations_to_relation", table_name="aqp_resource_relations")
    op.drop_index("ix_aqp_resource_relations_relation", table_name="aqp_resource_relations")
    op.drop_index("ix_aqp_resource_relations_to_id", table_name="aqp_resource_relations")
    op.drop_index("ix_aqp_resource_relations_from_id", table_name="aqp_resource_relations")
    op.drop_table("aqp_resource_relations")

    op.drop_index("ix_aqp_resources_workspace_type", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_owner_type", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_project_id", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_workspace_id", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_owner_user_id", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_visibility", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_owner_scope_id", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_owner_scope_kind", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_uri", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_resource_type", table_name="aqp_resources")
    op.drop_index("ix_aqp_resources_slug", table_name="aqp_resources")
    op.drop_table("aqp_resources")
