"""SEC filings ↔ Postgres lineage helpers."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource, Instrument, SecFiling

logger = logging.getLogger(__name__)


def upsert_sec_filing(record: dict[str, Any]) -> SecFiling | None:
    """Create or refresh a :class:`SecFiling` row from a filing dict.

    ``record`` is a normalized dict with the keys: ``cik``,
    ``accession_no``, ``form``, ``filed_at``, ``period_of_report``,
    ``primary_doc_url``, ``primary_doc_type``, ``xbrl_available``,
    ``items``, ``text_storage_uri``, ``instrument_vt_symbol`` (optional
    hint), plus an arbitrary ``meta`` dict.
    """
    accession_no = str(record.get("accession_no") or "").strip()
    if not accession_no:
        return None
    try:
        with get_session() as session:
            row = session.execute(
                select(SecFiling).where(SecFiling.accession_no == accession_no).limit(1)
            ).scalar_one_or_none()
            source_id = _sec_source_id(session)
            instrument_id = _resolve_instrument_id(
                session,
                cik=record.get("cik"),
                vt_symbol=record.get("instrument_vt_symbol"),
                ticker=record.get("ticker"),
            )

            filed_at = _parse_dt(record.get("filed_at"))
            period_of_report = _parse_dt(record.get("period_of_report"))
            now = datetime.utcnow()

            if row is None:
                row = SecFiling(
                    cik=str(record.get("cik") or "").strip(),
                    instrument_id=instrument_id,
                    accession_no=accession_no,
                    form=str(record.get("form") or "").strip(),
                    filed_at=filed_at or now,
                    period_of_report=period_of_report,
                    primary_doc_url=record.get("primary_doc_url"),
                    primary_doc_type=record.get("primary_doc_type"),
                    xbrl_available=bool(record.get("xbrl_available")),
                    items=list(record.get("items") or []),
                    text_storage_uri=record.get("text_storage_uri"),
                    source_id=source_id,
                    meta=dict(record.get("meta") or {}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                session.expunge(row)
                return row

            if instrument_id and not row.instrument_id:
                row.instrument_id = instrument_id
            if filed_at:
                row.filed_at = filed_at
            if period_of_report:
                row.period_of_report = period_of_report
            if record.get("primary_doc_url"):
                row.primary_doc_url = record["primary_doc_url"]
            if record.get("primary_doc_type"):
                row.primary_doc_type = record["primary_doc_type"]
            if record.get("xbrl_available") is not None:
                row.xbrl_available = bool(record["xbrl_available"])
            if record.get("items"):
                row.items = list(record["items"])
            if record.get("text_storage_uri"):
                row.text_storage_uri = record["text_storage_uri"]
            if source_id and not row.source_id:
                row.source_id = source_id
            if record.get("meta"):
                row.meta = {**(row.meta or {}), **record["meta"]}
            row.updated_at = now
            session.add(row)
            session.flush()
            session.expunge(row)
            return row
    except Exception:
        logger.warning(
            "upsert_sec_filing skipped for %s", accession_no, exc_info=True
        )
        return None


def _sec_source_id(session: Any) -> str | None:
    row = session.execute(
        select(DataSource).where(DataSource.name == "sec_edgar").limit(1)
    ).scalar_one_or_none()
    return row.id if row else None


def _resolve_instrument_id(
    session: Any,
    *,
    cik: Any,
    vt_symbol: str | None,
    ticker: str | None,
) -> str | None:
    if vt_symbol:
        row = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
        ).scalar_one_or_none()
        if row:
            return row.id
    if ticker:
        row = session.execute(
            select(Instrument).where(Instrument.ticker == ticker.upper()).limit(1)
        ).scalar_one_or_none()
        if row:
            return row.id
    if cik:
        cik_str = str(cik).lstrip("0") or str(cik)
        row = session.execute(
            select(Instrument).where(Instrument.identifiers["cik"].as_string() == cik_str).limit(1)
        ).scalar_one_or_none()
        if row:
            return row.id
    return None


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
