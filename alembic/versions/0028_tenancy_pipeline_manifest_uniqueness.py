"""Widen pipeline_manifests uniqueness to (workspace_id, namespace, name).

Revision ID: 0028_tenancy_pipeline_manifest_uniqueness
Revises: 0027_data_layer_medallion
Create Date: 2026-05-09

Two workspaces should each be able to ship a ``daily_ohlcv`` /
``daily_features`` / ``alpha_seed`` manifest in the same Iceberg
namespace without colliding on the legacy ``(namespace, name)``
constraint. The Alembic 0017 + 0018 migrations already added
``workspace_id`` to ``pipeline_manifests`` via :class:`ProjectScopedMixin`,
so this migration only swaps the unique index — no schema additions.

Pre-tenancy rows have ``workspace_id IS NULL``; the new constraint
treats those as a single tenancy bucket (matching their behaviour
under the old constraint), so the migration is a strict superset of
the previous integrity rule and never raises on existing data.
"""
from __future__ import annotations

from alembic import op


revision = "0028_tenancy_manifest_uq"
down_revision = "0027_data_layer_medallion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy unique constraint name is "uq_pipeline_manifests_ns_name".
    # Drop it and replace with the wider (workspace_id, namespace, name)
    # constraint. ``op.drop_constraint`` is idempotent when wrapped in a
    # try/except for fresh databases that never carried the legacy
    # constraint (e.g. those bootstrapped from an SQLite file).
    try:
        op.drop_constraint(
            "uq_pipeline_manifests_ns_name",
            "pipeline_manifests",
            type_="unique",
        )
    except Exception:
        # Constraint may not exist on older SQLite-backed dev DBs.
        pass

    op.create_unique_constraint(
        "uq_pipeline_manifests_ws_ns_name",
        "pipeline_manifests",
        ["workspace_id", "namespace", "name"],
    )


def downgrade() -> None:
    try:
        op.drop_constraint(
            "uq_pipeline_manifests_ws_ns_name",
            "pipeline_manifests",
            type_="unique",
        )
    except Exception:
        pass

    op.create_unique_constraint(
        "uq_pipeline_manifests_ns_name",
        "pipeline_manifests",
        ["namespace", "name"],
    )
