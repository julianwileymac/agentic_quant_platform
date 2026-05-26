"""Cell registry — application-layer / data-layer composition unit.

Revision ID: 0082_cell_registry
Revises: 0081_mlops_skills_and_artifacts
Create Date: 2026-05-25

Phase 3 §6.2 (RESTRUCTURING_PLAN.md) — cell topology layered on top
of the existing ``TenancyStrategy`` (Alembic 0063 / 0064).

A "cell" is the deployment-layer unit that composes with the
application-layer ``TenancyStrategy``:

  shared-std    -> shared_schema_rls         (one ns, many tenants, RLS)
  shared-prem   -> schema_per_tenant         (one ns, one schema/tenant)
  silo-reg      -> database_per_enterprise   (one ns, one tenant, own DB)
  silo-custom   -> hybrid                    (per-contract)

Two tables land here:

- ``cells`` — one row per cell. Mirrors the
  ``aqp_platform/configs/deployment/topology.yaml::cells`` section
  shape 1:1 (the YAML is the bootstrap seed; this table is the
  live source of truth once the control plane is up).
- ``cell_tenants`` — pinning table mapping tenant ids to cells with
  a placement state so the cell-router can do sub-millisecond
  lookups during request resolution.

The control-plane ``/manage/cells/*`` routes (Phase 3 §6.2) mutate
both tables behind the ``WorkloadRuntime`` audit ledger.

Per AGENTS rule 6 this migration is immutable once shipped — bugs
land in follow-up migrations.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0082_cell_registry"
down_revision = "0081_mlops_skills_and_artifacts"
branch_labels = None
depends_on = None


# Allow-listed values mirrored from
# ``aqp_platform_core.topology.models``. We use VARCHAR + CHECK rather
# than Postgres ENUM so SQLite test fixtures keep working without a
# dialect-specific ENUM type.
_CELL_TIERS = ("shared-std", "shared-prem", "silo-reg", "silo-custom")
_TENANCY_STRATEGIES = (
    "shared_schema_rls",
    "schema_per_tenant",
    "database_per_enterprise",
    "hybrid",
)
_CELL_STATES = (
    "provisioning",
    "active",
    "draining",
    "suspended",
    "maintenance",
    "decommissioning",
    "archived",
)
_PLACEMENT_STATES = ("active", "draining", "migrated", "evicted")


def upgrade() -> None:
    op.create_table(
        "cells",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("tenancy_strategy", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("availability_zone", sa.String(64), nullable=False),
        sa.Column("k8s_namespace", sa.String(63), nullable=False),
        sa.Column(
            "capacity_max_tenants",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
            server_default="provisioning",
        ),
        sa.Column(
            "pinned_tenants",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "routes",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "labels",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "annotations",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "last_modified_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state_transitioned_at", sa.DateTime, nullable=True),
        sa.Column("drained_at", sa.DateTime, nullable=True),
        sa.Column("decommissioned_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "tier IN ('" + "','".join(_CELL_TIERS) + "')",
            name="ck_cells_tier",
        ),
        sa.CheckConstraint(
            "tenancy_strategy IN ('" + "','".join(_TENANCY_STRATEGIES) + "')",
            name="ck_cells_tenancy_strategy",
        ),
        sa.CheckConstraint(
            "state IN ('" + "','".join(_CELL_STATES) + "')",
            name="ck_cells_state",
        ),
        sa.CheckConstraint(
            "capacity_max_tenants >= 1",
            name="ck_cells_capacity_min_one",
        ),
    )
    op.create_index("ix_cells_tier", "cells", ["tier"])
    op.create_index("ix_cells_region", "cells", ["region"])
    op.create_index("ix_cells_state", "cells", ["state"])
    op.create_index(
        "ix_cells_k8s_namespace",
        "cells",
        ["k8s_namespace"],
        unique=True,
    )

    op.create_table(
        "cell_tenants",
        sa.Column(
            "cell_id",
            sa.String(120),
            sa.ForeignKey("cells.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column(
            "placement",
            sa.String(32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "placed_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("drained_at", sa.DateTime, nullable=True),
        sa.Column("migrated_to_cell_id", sa.String(120), nullable=True),
        sa.PrimaryKeyConstraint("cell_id", "tenant_id", name="pk_cell_tenants"),
        sa.CheckConstraint(
            "placement IN ('" + "','".join(_PLACEMENT_STATES) + "')",
            name="ck_cell_tenants_placement",
        ),
    )
    op.create_index(
        "ix_cell_tenants_tenant_id", "cell_tenants", ["tenant_id"]
    )
    op.create_index(
        "ix_cell_tenants_placement", "cell_tenants", ["placement"]
    )


def downgrade() -> None:
    op.drop_index("ix_cell_tenants_placement", table_name="cell_tenants")
    op.drop_index("ix_cell_tenants_tenant_id", table_name="cell_tenants")
    op.drop_table("cell_tenants")

    op.drop_index("ix_cells_k8s_namespace", table_name="cells")
    op.drop_index("ix_cells_state", table_name="cells")
    op.drop_index("ix_cells_region", table_name="cells")
    op.drop_index("ix_cells_tier", table_name="cells")
    op.drop_table("cells")
