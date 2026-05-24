"""AirbyteDataset kind backfill (Phase 1, plan section 5).

Revision ID: 0072_airbyte_dataset_kind
Revises: 0071_databento_iex_broker_providers
Create Date: 2026-05-24

Closes the rule-29 gap documented in the planning exploration:
Airbyte-synced data had no typed `BaseDataset` kind. The new
:class:`aqp.data.datasets.kinds.airbyte.AirbyteDataset` ships with
this migration; the migration backfills existing
:class:`aqp.persistence.models_airbyte.AirbyteConnectionRow` rows
into :class:`aqp.persistence.models.DatasetCatalog` with
``dataset_kind='airbyte'``, ``is_ingested=True`` for connections
whose last sync succeeded, and the canonical
``aqp_bronze_airbyte_<connector_slug>`` namespace.

The backfill is idempotent — it only inserts rows whose
``(provider, name)`` pair isn't already in the catalog so re-running
on a partially-migrated cluster is safe.

Per AGENTS rule 6: immutable once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0072_airbyte_dataset_kind"
down_revision = "0071_databento_iex_broker_providers"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    # Read existing Airbyte connections + back-fill dataset_catalogs.
    rows = bind.execute(
        sa.text(
            """
            SELECT id::text, name, connector_id, namespace,
                   last_sync_status, workspace_id, owner_user_id
              FROM airbyte_connections
            """
        )
    ).fetchall()
    if not rows:
        return

    for row in rows:
        connector_slug = (
            str(row.connector_id or row.name or "unknown")
            .strip()
            .lower()
            .replace("-", "_")
        )
        bronze_ns = f"aqp_bronze_airbyte_{connector_slug}"
        external_spec_json = sa.text(
            "CAST(:val AS JSONB)" if _is_postgres() else "CAST(:val AS JSON)"
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO dataset_catalogs (
                    id, name, provider, dataset_kind, is_ingested,
                    iceberg_identifier, medallion_layer,
                    workspace_id, owner_user_id, external_spec_json
                )
                SELECT
                    :id, :name, :provider, 'airbyte',
                    :is_ingested, :iceberg_identifier, 'bronze',
                    :workspace_id, :owner_user_id, :external_spec_json
                WHERE NOT EXISTS (
                    SELECT 1 FROM dataset_catalogs
                    WHERE provider = :provider AND name = :name
                )
                """
            ).bindparams(
                sa.bindparam("external_spec_json", type_=sa.JSON),
            ),
            {
                "id": f"airbyte:{row.id}",
                "name": str(row.name or connector_slug),
                "provider": "airbyte",
                "is_ingested": str(row.last_sync_status or "")
                .strip()
                .lower()
                == "succeeded",
                "iceberg_identifier": f"{bronze_ns}.{row.name or 'default'}",
                "workspace_id": row.workspace_id,
                "owner_user_id": row.owner_user_id,
                "external_spec_json": {
                    "workspace_id": row.workspace_id,
                    "connection_id": row.id,
                    "stream": row.name or "default",
                    "connector_slug": connector_slug,
                    "bronze_namespace": bronze_ns,
                },
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM dataset_catalogs "
            "WHERE provider = 'airbyte' AND dataset_kind = 'airbyte'"
        )
    )
