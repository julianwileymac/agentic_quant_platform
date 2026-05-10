"""Self-service Airbyte builder — manifest storage on connector rows.

Revision ID: 0033_airbyte_manifest_storage
Revises: 0032_dataset_kind_ingestion_flag
Create Date: 2026-05-09

Phase 2 of the self-service data fabric expansion. Adds three
columns to :class:`aqp.persistence.models_airbyte.AirbyteConnectorRow`
so the visual builder can persist:

- ``manifest_yaml`` — the round-tripped Low-Code CDK YAML emitted
  from the form state. Stored TEXT so we keep linebreaks intact.
- ``aqp_fetcher_path`` — dotted module path
  (e.g. ``aqp.data.fetchers.userland.acme_quote``) when the user
  toggles "Custom Python" and the codegen writes a stub under
  ``aqp/data/fetchers/userland/``.
- ``builder_state_json`` — raw form state dict so re-opening the
  builder shows the same values without re-parsing the YAML.

No backfill — existing rows stay NULL until a builder edit lands.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0033_airbyte_manifest_storage"
down_revision = "0032_dataset_kind_ingestion_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "airbyte_connectors",
        sa.Column("manifest_yaml", sa.Text(), nullable=True),
    )
    op.add_column(
        "airbyte_connectors",
        sa.Column("aqp_fetcher_path", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "airbyte_connectors",
        sa.Column("builder_state_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("airbyte_connectors", "builder_state_json")
    op.drop_column("airbyte_connectors", "aqp_fetcher_path")
    op.drop_column("airbyte_connectors", "manifest_yaml")
