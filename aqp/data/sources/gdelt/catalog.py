"""GDelt mentions → Postgres bulk insert helpers."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource, GDeltMention

logger = logging.getLogger(__name__)


def upsert_gdelt_mentions(rows: list[dict[str, Any]]) -> int:
    """Upsert a batch of mention dicts into ``gdelt_mentions``.

    Returns the number of rows persisted (idempotent: duplicates on
    ``gkg_record_id`` + ``instrument_id`` pairs are skipped).
    """
    if not rows:
        return 0
    try:
        with get_session() as session:
            source_id = _gdelt_source_id(session)
            persisted = 0
            seen: set[tuple[str, str | None]] = set()
            for row in rows:
                gkg_record_id = str(row.get("gkg_record_id") or "").strip()
                if not gkg_record_id:
                    continue
                instrument_id = row.get("instrument_id")
                key = (gkg_record_id, instrument_id)
                if key in seen:
                    continue
                seen.add(key)

                # Dedup against DB for the unique gkg_record_id.
                existing = session.execute(
                    select(GDeltMention)
                    .where(GDeltMention.gkg_record_id == gkg_record_id)
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                date_value = _parse_dt(row.get("date"))
                mention = GDeltMention(
                    gkg_record_id=gkg_record_id,
                    date=date_value or datetime.utcnow(),
                    source_common_name=row.get("source_common_name"),
                    document_identifier=row.get("document_identifier"),
                    instrument_id=instrument_id,
                    themes=list(row.get("themes") or []),
                    tone=dict(row.get("tone") or {}),
                    organizations_match=list(row.get("organizations_match") or []),
                    source_id=source_id,
                    meta=dict(row.get("meta") or {}),
                    created_at=datetime.utcnow(),
                )
                session.add(mention)
                persisted += 1
            session.flush()
            return persisted
    except Exception:
        logger.warning("upsert_gdelt_mentions skipped", exc_info=True)
        return 0


def _gdelt_source_id(session: Any) -> str | None:
    row = session.execute(
        select(DataSource).where(DataSource.name == "gdelt").limit(1)
    ).scalar_one_or_none()
    return row.id if row else None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        ts = pd.Timestamp(value)
        return None if ts is pd.NaT else ts.to_pydatetime()
    except Exception:
        return None
