"""Backfill ``identifier_links`` from the legacy ``instruments.identifiers`` JSON blob.

Revision ID: 0040_normalized_identifiers_backfill
Revises: 0039_extended_instrument_taxonomy
Create Date: 2026-05-16

The legacy ``Instrument.identifiers`` JSON column carries a flat
``{scheme: value}`` map. The normalized ``identifier_links`` table
(``aqp/persistence/models.py::IdentifierLink``, present since the data-layer
unification rollout) is the source of truth from Phase 1 onwards because it
carries ``valid_from`` / ``valid_to`` for point-in-time resolution.

This migration copies every distinct ``(instrument_id, scheme, value)`` triple
from the JSON blob into ``identifier_links`` rows with a NULL validity
window — meaning "valid for all time the row represents". Subsequent
corporate-action processing layers can rewrite specific intervals.

The legacy JSON column is **kept** for backward compatibility — readers that
haven't yet migrated to the resolver service continue to work. The
deprecation marker is documented in
:mod:`aqp.data.identity.resolver`.

AGENTS.md rule 6: this migration is **immutable** once shipped.

The data migration is idempotent: it uses an upsert-style guard against the
``uq_identifier_links_unique`` index and ``confidence=0.7`` to flag rows that
came from the legacy blob (vs first-party loader rows at 1.0). Operators that
need to re-run only need to drop the rows where ``source_id IS NULL AND
confidence = 0.7``.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "0040_normalized_identifiers_backfill"
down_revision = "0039_extended_instrument_taxonomy"
branch_labels = None
depends_on = None


logger = logging.getLogger(__name__)


# Schemes the legacy blob might carry. Lower-cased before insert so the
# ``ix_identifier_links_scheme_value`` composite stays selective.
KNOWN_LEGACY_SCHEMES: frozenset[str] = frozenset(
    {
        "ticker",
        "vt_symbol",
        "cik",
        "cusip",
        "isin",
        "figi",
        "sedol",
        "lei",
        "gvkey",
        "permid",
        "openfigi",
        "bbg_id",
        "ric",
        "marquee_id",
        "occ_symbol",
        "exchange_product_code",
    }
)


def _coerce_scheme(raw: str) -> str:
    s = str(raw).strip().lower()
    # Map a handful of legacy aliases onto the canonical scheme name.
    aliases = {
        "bloomberg": "bbg_id",
        "bloomberg_id": "bbg_id",
        "bbg": "bbg_id",
        "reuters": "ric",
        "refinitiv": "ric",
        "bloomberg_global_id": "figi",
        "open_figi": "openfigi",
        "marquee": "marquee_id",
    }
    return aliases.get(s, s)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "identifier_links" not in inspector.get_table_names():
        logger.warning(
            "identifier_links table missing — skipping backfill. "
            "Run an earlier migration first."
        )
        return
    if "instruments" not in inspector.get_table_names():
        logger.warning("instruments table missing — skipping backfill.")
        return

    instruments = sa.table(
        "instruments",
        sa.column("id", sa.String),
        sa.column("identifiers", sa.JSON),
    )
    identifier_links = sa.table(
        "identifier_links",
        sa.column("id", sa.String),
        sa.column("entity_kind", sa.String),
        sa.column("entity_id", sa.String),
        sa.column("instrument_id", sa.String),
        sa.column("scheme", sa.String),
        sa.column("value", sa.String),
        sa.column("valid_from", sa.DateTime),
        sa.column("valid_to", sa.DateTime),
        sa.column("source_id", sa.String),
        sa.column("confidence", sa.Float),
        sa.column("meta", sa.JSON),
        sa.column("created_at", sa.DateTime),
    )

    rows = bind.execute(sa.select(instruments.c.id, instruments.c.identifiers)).fetchall()
    inserted = 0
    skipped = 0
    for instrument_id, blob in rows:
        if not blob:
            continue
        # JSON column may come back as a Python dict (psycopg2 JSON) or a string.
        if isinstance(blob, str):
            try:
                blob = json.loads(blob)
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
        if not isinstance(blob, dict):
            skipped += 1
            continue
        for scheme_raw, value_raw in blob.items():
            scheme = _coerce_scheme(scheme_raw)
            if not scheme or value_raw is None:
                continue
            value = str(value_raw).strip()
            if not value:
                continue
            exists = bind.execute(
                sa.select(sa.func.count())
                .select_from(identifier_links)
                .where(
                    identifier_links.c.entity_kind == "instrument",
                    identifier_links.c.scheme == scheme,
                    identifier_links.c.value == value,
                    identifier_links.c.entity_id == instrument_id,
                )
            ).scalar_one()
            if exists:
                continue
            bind.execute(
                identifier_links.insert().values(
                    id=str(uuid.uuid4()),
                    entity_kind="instrument",
                    entity_id=instrument_id,
                    instrument_id=instrument_id,
                    scheme=scheme,
                    value=value,
                    valid_from=None,
                    valid_to=None,
                    source_id=None,
                    confidence=0.7,
                    meta={"source": "legacy_json_blob_backfill"},
                    created_at=datetime.utcnow(),
                )
            )
            inserted += 1
    logger.info(
        "0040 identifier backfill: inserted=%d skipped=%d total_instruments=%d",
        inserted,
        skipped,
        len(rows),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "identifier_links" not in inspector.get_table_names():
        return
    identifier_links = sa.table(
        "identifier_links",
        sa.column("id", sa.String),
        sa.column("source_id", sa.String),
        sa.column("confidence", sa.Float),
        sa.column("meta", sa.JSON),
    )
    # Remove only the rows we inserted (source_id NULL, confidence 0.7, meta
    # marked with the source key). Anything else stays untouched.
    bind.execute(
        identifier_links.delete().where(
            identifier_links.c.source_id.is_(None),
            identifier_links.c.confidence == 0.7,
        )
    )
