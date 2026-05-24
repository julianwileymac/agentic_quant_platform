"""PostgreSQL helpers for pipeline state and loading."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_safe_identifier(value: str) -> bool:
    return bool(SAFE_IDENTIFIER.match(value))


def ensure_pipeline_tables(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_cdc_state (
                pipeline_name TEXT PRIMARY KEY,
                watermark TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01T00:00:00Z',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_cdc_records (
                pipeline_name TEXT NOT NULL,
                source_table TEXT NOT NULL,
                source_pk TEXT NOT NULL,
                payload JSONB NOT NULL,
                source_updated_at TIMESTAMPTZ,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (pipeline_name, source_table, source_pk)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_vector_audit (
                pipeline_name TEXT NOT NULL,
                source_key TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                sink_name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (pipeline_name, source_key, chunk_id, sink_name)
            );
            """
        )
    conn.commit()


def get_watermark(
    conn: psycopg.Connection[Any],
    pipeline_name: str,
) -> datetime:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT watermark
            FROM pipeline_cdc_state
            WHERE pipeline_name = %s
            """,
            (pipeline_name,),
        )
        row = cur.fetchone()
    if row and row["watermark"]:
        return row["watermark"]
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def update_watermark(
    conn: psycopg.Connection[Any],
    pipeline_name: str,
    watermark: datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_cdc_state (pipeline_name, watermark, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (pipeline_name)
            DO UPDATE SET watermark = EXCLUDED.watermark, updated_at = NOW()
            """,
            (pipeline_name, watermark),
        )
    conn.commit()


def upsert_cdc_payload(
    conn: psycopg.Connection[Any],
    pipeline_name: str,
    source_table: str,
    source_pk: str,
    payload: dict[str, Any],
    source_updated_at: datetime | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_cdc_records (
                pipeline_name, source_table, source_pk, payload, source_updated_at, loaded_at
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
            ON CONFLICT (pipeline_name, source_table, source_pk)
            DO UPDATE SET
                payload = EXCLUDED.payload,
                source_updated_at = EXCLUDED.source_updated_at,
                loaded_at = NOW()
            """,
            (
                pipeline_name,
                source_table,
                source_pk,
                json.dumps(payload),
                source_updated_at,
            ),
        )
    conn.commit()


def insert_vector_audit(
    conn: psycopg.Connection[Any],
    pipeline_name: str,
    source_key: str,
    chunk_id: str,
    sink_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_vector_audit (pipeline_name, source_key, chunk_id, sink_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (pipeline_name, source_key, chunk_id, sink_name)
            DO NOTHING
            """,
            (pipeline_name, source_key, chunk_id, sink_name),
        )
    conn.commit()

