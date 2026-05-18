"""Canonical metadata aspect store (DataHub-style).

Revision ID: 0048_metadata_aspects
Revises: 0047_data_fabric_foundation
Create Date: 2026-05-17
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0048_metadata_aspects"
down_revision = "0047_data_fabric_foundation"
branch_labels = None
depends_on = None

_JSON_COMPAT = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
_ENTITY_KIND_SANITISER = re.compile(r"[^a-z0-9_]+")
_MIGRATION_ACTOR = "migration:0048_metadata_aspects"


def _uuid() -> str:
    return str(uuid.uuid4())


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _safe_entity_kind(kind: str | None) -> str:
    cleaned = _ENTITY_KIND_SANITISER.sub("_", str(kind or "entity").strip().lower()).strip("_")
    return cleaned or "entity"


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT to_regclass(:table_name)"),
        {"table_name": table_name},
    ).scalar_one_or_none()
    return result is not None


def _insert_metadata_entity(
    bind: sa.Connection,
    *,
    urn: str,
    entity_type: str,
    created_at: datetime | None,
    updated_at: datetime | None,
    owner_user_id: str | None,
    workspace_id: str | None,
    project_id: str | None,
) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO metadata_entities (
                urn,
                entity_type,
                created_at,
                updated_at,
                owner_user_id,
                workspace_id,
                project_id
            )
            VALUES (
                :urn,
                :entity_type,
                :created_at,
                :updated_at,
                :owner_user_id,
                :workspace_id,
                :project_id
            )
            ON CONFLICT (urn) DO NOTHING
            """
        ),
        {
            "urn": urn,
            "entity_type": entity_type,
            "created_at": created_at or datetime.utcnow(),
            "updated_at": updated_at or datetime.utcnow(),
            "owner_user_id": owner_user_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )


def _insert_entity_aspect(
    bind: sa.Connection,
    *,
    urn: str,
    aspect_name: str,
    version: int,
    payload: dict[str, Any],
    created_at: datetime | None,
    owner_user_id: str | None,
    workspace_id: str | None,
    project_id: str | None,
    system_metadata: dict[str, Any] | None = None,
) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO entity_aspects (
                id,
                urn,
                aspect_name,
                version,
                payload,
                payload_hash,
                system_metadata,
                created_at,
                created_by,
                owner_user_id,
                workspace_id,
                project_id
            )
            VALUES (
                :id,
                :urn,
                :aspect_name,
                :version,
                :payload,
                :payload_hash,
                :system_metadata,
                :created_at,
                :created_by,
                :owner_user_id,
                :workspace_id,
                :project_id
            )
            ON CONFLICT ON CONSTRAINT uq_entity_aspects_urn_name_version DO NOTHING
            """
        ),
        {
            "id": _uuid(),
            "urn": urn,
            "aspect_name": aspect_name,
            "version": int(version),
            # psycopg2 can't adapt Python dicts directly; JSON-encode
            # for the JSONB column. (Hot-patch to the never-applied
            # migration — see 0046 hot-patch note.)
            "payload": json.dumps(payload, sort_keys=True),
            "payload_hash": _payload_hash(payload),
            "system_metadata": json.dumps(dict(system_metadata or {}), sort_keys=True),
            "created_at": created_at or datetime.utcnow(),
            "created_by": _MIGRATION_ACTOR,
            "owner_user_id": owner_user_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )


def _backfill_dataset_catalog(bind: sa.Connection) -> None:
    if not _table_exists(bind, "dataset_catalogs"):
        return

    # Older databases (pre-0017 tenancy rollout) may not have the
    # ProjectScopedMixin columns on dataset_catalogs. Detect at runtime
    # and use NULL placeholders so the backfill still emits aspects
    # (without tenancy stamps). Hot-patch to the never-successfully-
    # applied migration — see 0046 hot-patch note.
    inspector = sa.inspect(bind)
    cols = {col["name"] for col in inspector.get_columns("dataset_catalogs")}
    owner_expr = "owner_user_id" if "owner_user_id" in cols else "NULL AS owner_user_id"
    ws_expr = "workspace_id" if "workspace_id" in cols else "NULL AS workspace_id"
    project_expr = "project_id" if "project_id" in cols else "NULL AS project_id"

    rows = bind.execute(
        sa.text(
            f"""
            SELECT
                id,
                name,
                provider,
                domain,
                frequency,
                storage_uri,
                description,
                tags,
                schema_json,
                meta,
                iceberg_identifier,
                medallion_layer,
                business_metadata,
                data_contract_json,
                created_at,
                updated_at,
                {owner_expr},
                {ws_expr},
                {project_expr}
            FROM dataset_catalogs
            WHERE iceberg_identifier IS NOT NULL
              AND iceberg_identifier <> ''
            ORDER BY iceberg_identifier, created_at, id
            """
        )
    ).mappings()

    versions: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        urn = f"urn:aqp:dataset:prod:{row['iceberg_identifier']}"
        _insert_metadata_entity(
            bind,
            urn=urn,
            entity_type="dataset",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
        )

        dataset_properties = {
            "dataset_id": row["id"],
            "name": row["name"],
            "provider": row["provider"],
            "domain": row["domain"],
            "frequency": row["frequency"],
            "storage_uri": row["storage_uri"],
            "description": row["description"],
            "tags": row["tags"] or [],
            "schema_json": row["schema_json"] or {},
            "meta": row["meta"] or {},
            "iceberg_identifier": row["iceberg_identifier"],
            "medallion_layer": row["medallion_layer"],
        }
        business_metadata = dict(row["business_metadata"] or {})
        data_contract = dict(row["data_contract_json"] or {})

        for aspect_name, payload in (
            ("datasetProperties", dataset_properties),
            ("businessMetadata", business_metadata),
            ("dataContract", data_contract),
        ):
            versions[(urn, aspect_name)] += 1
            _insert_entity_aspect(
                bind,
                urn=urn,
                aspect_name=aspect_name,
                version=versions[(urn, aspect_name)],
                payload=payload,
                created_at=row["created_at"],
                owner_user_id=row["owner_user_id"],
                workspace_id=row["workspace_id"],
                project_id=row["project_id"],
                system_metadata={"legacy_table": "dataset_catalogs"},
            )


def _backfill_entity_registry(bind: sa.Connection) -> None:
    if not _table_exists(bind, "entities"):
        return

    # Defensive tenancy-column check (see 0046 / dataset_catalog
    # hot-patch note) — older DBs predate ProjectScopedMixin on entities.
    inspector_e = sa.inspect(bind)
    cols_e = {col["name"] for col in inspector_e.get_columns("entities")}
    owner_expr_e = "owner_user_id" if "owner_user_id" in cols_e else "NULL AS owner_user_id"
    ws_expr_e = "workspace_id" if "workspace_id" in cols_e else "NULL AS workspace_id"
    project_expr_e = "project_id" if "project_id" in cols_e else "NULL AS project_id"

    rows = bind.execute(
        sa.text(
            f"""
            SELECT
                id,
                kind,
                canonical_name,
                short_name,
                primary_identifier,
                primary_identifier_scheme,
                instrument_id,
                issuer_id,
                description,
                attributes,
                tags,
                confidence,
                source_dataset,
                source_extractor,
                is_canonical,
                parent_id,
                created_at,
                updated_at,
                {owner_expr_e},
                {ws_expr_e},
                {project_expr_e}
            FROM entities
            ORDER BY id
            """
        )
    ).mappings()

    versions: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        kind = _safe_entity_kind(row["kind"])
        urn = f"urn:aqp:{kind}:prod:{row['id']}"
        _insert_metadata_entity(
            bind,
            urn=urn,
            entity_type=kind,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
        )

        payload = {
            "id": row["id"],
            "kind": row["kind"],
            "canonical_name": row["canonical_name"],
            "short_name": row["short_name"],
            "primary_identifier": row["primary_identifier"],
            "primary_identifier_scheme": row["primary_identifier_scheme"],
            "instrument_id": row["instrument_id"],
            "issuer_id": row["issuer_id"],
            "description": row["description"],
            "attributes": row["attributes"] or {},
            "tags": row["tags"] or [],
            "confidence": row["confidence"],
            "source_dataset": row["source_dataset"],
            "source_extractor": row["source_extractor"],
            "is_canonical": row["is_canonical"],
            "parent_id": row["parent_id"],
        }

        versions[(urn, "entityProperties")] += 1
        _insert_entity_aspect(
            bind,
            urn=urn,
            aspect_name="entityProperties",
            version=versions[(urn, "entityProperties")],
            payload=payload,
            created_at=row["created_at"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
            system_metadata={"legacy_table": "entities"},
        )


def _backfill_lineage_events(bind: sa.Connection) -> None:
    if not _table_exists(bind, "data_lineage_events"):
        return

    # Defensive tenancy-column check (see 0046 / dataset_catalog
    # hot-patch note).
    inspector_l = sa.inspect(bind)
    cols_l = {col["name"] for col in inspector_l.get_columns("data_lineage_events")}
    owner_expr_l = "owner_user_id" if "owner_user_id" in cols_l else "NULL AS owner_user_id"
    ws_expr_l = "workspace_id" if "workspace_id" in cols_l else "NULL AS workspace_id"
    project_expr_l = "project_id" if "project_id" in cols_l else "NULL AS project_id"

    rows = bind.execute(
        sa.text(
            f"""
            SELECT
                id,
                source_table_id,
                target_table_id,
                transform_kind,
                actor,
                actor_kind,
                run_id,
                manifest_id,
                mcp_tool_name,
                service_name,
                rows_written,
                medallion_layer,
                summary,
                details_json,
                created_at,
                {owner_expr_l},
                {ws_expr_l},
                {project_expr_l}
            FROM data_lineage_events
            ORDER BY created_at, id
            """
        )
    ).mappings()

    versions: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        urn = f"urn:aqp:lineage_event:prod:{row['id']}"
        _insert_metadata_entity(
            bind,
            urn=urn,
            entity_type="lineage_event",
            created_at=row["created_at"],
            updated_at=row["created_at"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
        )

        payload = {
            "id": row["id"],
            "source_table_id": row["source_table_id"],
            "target_table_id": row["target_table_id"],
            "transform_kind": row["transform_kind"],
            "actor": row["actor"],
            "actor_kind": row["actor_kind"],
            "run_id": row["run_id"],
            "manifest_id": row["manifest_id"],
            "mcp_tool_name": row["mcp_tool_name"],
            "service_name": row["service_name"],
            "rows_written": row["rows_written"],
            "medallion_layer": row["medallion_layer"],
            "summary": row["summary"],
            "details_json": row["details_json"] or {},
        }
        versions[(urn, "lineageEdge")] += 1
        _insert_entity_aspect(
            bind,
            urn=urn,
            aspect_name="lineageEdge",
            version=versions[(urn, "lineageEdge")],
            payload=payload,
            created_at=row["created_at"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"],
            system_metadata={"legacy_table": "data_lineage_events"},
        )


def _run_postgres_backfill(bind: sa.Connection) -> None:
    _backfill_dataset_catalog(bind)
    _backfill_entity_registry(bind)
    _backfill_lineage_events(bind)


def upgrade() -> None:
    op.create_table(
        "metadata_entities",
        sa.Column("urn", sa.String(length=280), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
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
        "ix_metadata_entities_entity_type",
        "metadata_entities",
        ["entity_type"],
    )
    op.create_index(
        "ix_metadata_entities_owner_user_id",
        "metadata_entities",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_metadata_entities_workspace_id",
        "metadata_entities",
        ["workspace_id"],
    )
    op.create_index(
        "ix_metadata_entities_project_id",
        "metadata_entities",
        ["project_id"],
    )

    op.create_table(
        "entity_aspects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("urn", sa.String(length=280), nullable=False),
        sa.Column("aspect_name", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", _JSON_COMPAT, nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("system_metadata", _JSON_COMPAT, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["urn"],
            ["metadata_entities.urn"],
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
        sa.UniqueConstraint(
            "urn",
            "aspect_name",
            "version",
            name="uq_entity_aspects_urn_name_version",
        ),
        sa.UniqueConstraint(
            "urn",
            "aspect_name",
            "payload_hash",
            name="uq_entity_aspects_urn_name_hash",
        ),
    )
    op.create_index("ix_entity_aspects_urn", "entity_aspects", ["urn"])
    op.create_index(
        "ix_entity_aspects_aspect_name",
        "entity_aspects",
        ["aspect_name"],
    )
    op.create_index(
        "ix_entity_aspects_payload_hash",
        "entity_aspects",
        ["payload_hash"],
    )
    op.create_index(
        "ix_entity_aspects_created_at",
        "entity_aspects",
        ["created_at"],
    )
    op.create_index(
        "ix_entity_aspects_owner_user_id",
        "entity_aspects",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_entity_aspects_workspace_id",
        "entity_aspects",
        ["workspace_id"],
    )
    op.create_index(
        "ix_entity_aspects_project_id",
        "entity_aspects",
        ["project_id"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _run_postgres_backfill(bind)


def downgrade() -> None:
    op.drop_index("ix_entity_aspects_project_id", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_workspace_id", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_owner_user_id", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_created_at", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_payload_hash", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_aspect_name", table_name="entity_aspects")
    op.drop_index("ix_entity_aspects_urn", table_name="entity_aspects")
    op.drop_table("entity_aspects")

    op.drop_index("ix_metadata_entities_project_id", table_name="metadata_entities")
    op.drop_index("ix_metadata_entities_workspace_id", table_name="metadata_entities")
    op.drop_index("ix_metadata_entities_owner_user_id", table_name="metadata_entities")
    op.drop_index("ix_metadata_entities_entity_type", table_name="metadata_entities")
    op.drop_table("metadata_entities")

