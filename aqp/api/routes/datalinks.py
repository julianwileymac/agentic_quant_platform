"""Data availability summary endpoint.

Aggregates the ``data_links`` table into a human-friendly "what data do
we have for this instrument?" response that's cheap to compute and
renders well in the UI's instrument detail page.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DataLink,
    DataSource,
    DatasetCatalog,
    DatasetVersion,
    Instrument,
)

router = APIRouter(tags=["data-links"])


class DataAvailabilityRow(BaseModel):
    source_name: str | None = None
    source_display_name: str | None = None
    domain: str
    dataset_name: str | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    row_count: int = 0
    dataset_versions: int = 0


class DataAvailabilityResponse(BaseModel):
    vt_symbol: str
    instrument_id: str
    rows: list[DataAvailabilityRow] = Field(default_factory=list)


@router.get(
    "/instruments/{vt_symbol}/data",
    response_model=DataAvailabilityResponse,
)
def instrument_data_summary(vt_symbol: str) -> DataAvailabilityResponse:
    with get_session() as session:
        instrument = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
        ).scalar_one_or_none()
        if instrument is None:
            raise HTTPException(404, f"instrument {vt_symbol!r} not found")

        stmt = (
            select(
                DataSource.name.label("source_name"),
                DataSource.display_name.label("source_display_name"),
                DatasetCatalog.domain.label("domain"),
                DatasetCatalog.name.label("dataset_name"),
                func.min(DataLink.coverage_start).label("coverage_start"),
                func.max(DataLink.coverage_end).label("coverage_end"),
                func.sum(DataLink.row_count).label("row_count"),
                func.count(DataLink.id).label("dataset_versions"),
            )
            .select_from(DataLink)
            .join(DatasetVersion, DatasetVersion.id == DataLink.dataset_version_id)
            .join(DatasetCatalog, DatasetCatalog.id == DatasetVersion.catalog_id)
            .outerjoin(DataSource, DataSource.id == DataLink.source_id)
            .where(DataLink.instrument_id == instrument.id)
            .group_by(
                DataSource.name,
                DataSource.display_name,
                DatasetCatalog.domain,
                DatasetCatalog.name,
            )
            .order_by(
                DatasetCatalog.domain,
                DataSource.name,
            )
        )
        rows = session.execute(stmt).all()
        return DataAvailabilityResponse(
            vt_symbol=instrument.vt_symbol,
            instrument_id=instrument.id,
            rows=[
                DataAvailabilityRow(
                    source_name=row.source_name,
                    source_display_name=row.source_display_name,
                    domain=row.domain,
                    dataset_name=row.dataset_name,
                    coverage_start=row.coverage_start,
                    coverage_end=row.coverage_end,
                    row_count=int(row.row_count or 0),
                    dataset_versions=int(row.dataset_versions or 0),
                )
                for row in rows
            ],
        )
