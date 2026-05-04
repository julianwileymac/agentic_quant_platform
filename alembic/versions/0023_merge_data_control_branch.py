"""Merge data-control-metadata branch into main migration line.

Revision ID: 0023_merge_data_control_branch
Revises: 0022_mlops_experiment_runs, 0020_data_control_metadata
Create Date: 2026-05-03

Migrations 0020_bots and 0020_data_control_metadata both branched off
0019_ownership_enforce. The bots branch carried forward through
0021_default_tenancy and 0022_mlops_experiment_runs, while the data-
control branch became orphaned. This empty merge revision converges
both heads so subsequent migrations have a single linear ancestor.
"""
from __future__ import annotations

revision = "0023_merge_data_control_branch"
down_revision = ("0022_mlops_experiment_runs", "0020_data_control_metadata")
branch_labels = None
depends_on = None


def upgrade() -> None:  # pragma: no cover - structural merge, no DDL
    pass


def downgrade() -> None:  # pragma: no cover - structural merge, no DDL
    pass
