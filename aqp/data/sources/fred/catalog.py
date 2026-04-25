"""FRED series ↔ Postgres lineage helpers."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from aqp.persistence.db import get_session
from aqp.persistence.models import DataSource, FredSeries

logger = logging.getLogger(__name__)


def upsert_fred_series(metadata: dict[str, Any]) -> FredSeries | None:
    """Create or refresh a :class:`FredSeries` row from a FRED API record.

    ``metadata`` is expected to be the dict FRED returns from
    ``fred/series`` — the keys are ``id``, ``title``, ``units``,
    ``units_short``, ``frequency``, ``frequency_short``,
    ``seasonal_adjustment``, ``seasonal_adjustment_short``,
    ``observation_start``, ``observation_end``, ``last_updated``,
    ``popularity``, ``notes``, ``release_id``, etc.
    """
    series_id = str(metadata.get("id") or metadata.get("series_id") or "").strip()
    if not series_id:
        return None

    try:
        with get_session() as session:
            row = session.execute(
                select(FredSeries).where(FredSeries.series_id == series_id).limit(1)
            ).scalar_one_or_none()
            source_id = _fred_source_id(session)
            title = str(metadata.get("title") or "").strip()
            units = metadata.get("units")
            units_short = metadata.get("units_short")
            frequency = metadata.get("frequency")
            frequency_short = metadata.get("frequency_short")
            seasonal_adj = metadata.get("seasonal_adjustment")
            seasonal_adj_short = metadata.get("seasonal_adjustment_short")
            category_id = _maybe_int(metadata.get("category_id"))
            release_id = _maybe_int(metadata.get("release_id"))
            popularity = _maybe_int(metadata.get("popularity"))
            notes = metadata.get("notes")
            observation_start = _parse_date(metadata.get("observation_start"))
            observation_end = _parse_date(metadata.get("observation_end"))
            last_updated = _parse_datetime(metadata.get("last_updated"))
            now = datetime.utcnow()

            if row is None:
                row = FredSeries(
                    series_id=series_id,
                    title=title,
                    units=units,
                    units_short=units_short,
                    frequency=frequency,
                    frequency_short=frequency_short,
                    seasonal_adj=seasonal_adj,
                    seasonal_adj_short=seasonal_adj_short,
                    category_id=category_id,
                    release_id=release_id,
                    source_id=source_id,
                    observation_start=observation_start,
                    observation_end=observation_end,
                    popularity=popularity,
                    notes=notes,
                    last_updated=last_updated,
                    meta=dict(metadata),
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
                session.expunge(row)
                return row

            row.title = title or row.title
            row.units = units or row.units
            row.units_short = units_short or row.units_short
            row.frequency = frequency or row.frequency
            row.frequency_short = frequency_short or row.frequency_short
            row.seasonal_adj = seasonal_adj or row.seasonal_adj
            row.seasonal_adj_short = seasonal_adj_short or row.seasonal_adj_short
            if category_id is not None:
                row.category_id = category_id
            if release_id is not None:
                row.release_id = release_id
            if source_id and not row.source_id:
                row.source_id = source_id
            if observation_start:
                row.observation_start = observation_start
            if observation_end:
                row.observation_end = observation_end
            if popularity is not None:
                row.popularity = popularity
            if notes:
                row.notes = notes
            if last_updated:
                row.last_updated = last_updated
            row.meta = {**(row.meta or {}), **metadata}
            row.updated_at = now
            session.add(row)
            session.flush()
            session.expunge(row)
            return row
    except Exception:
        logger.warning("upsert_fred_series skipped for %s", series_id, exc_info=True)
        return None


def _fred_source_id(session: Any) -> str | None:
    row = session.execute(
        select(DataSource).where(DataSource.name == "fred").limit(1)
    ).scalar_one_or_none()
    return row.id if row else None


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return pd.Timestamp(value).to_pydatetime()
    except Exception:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    return _parse_date(value)
