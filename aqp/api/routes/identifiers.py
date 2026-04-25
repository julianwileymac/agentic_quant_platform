"""Identifier graph endpoints.

Bridges the canonical :class:`aqp.persistence.models.Instrument` rows
with the :class:`aqp.persistence.models.IdentifierLink` graph so the UI
(and agent tooling) can reason about a security through any scheme —
ticker, vt_symbol, CIK, CUSIP, ISIN, FIGI, LEI, ...
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.sources.resolvers.identifiers import IdentifierResolver
from aqp.persistence.db import get_session
from aqp.persistence.models import Instrument

router = APIRouter(prefix="/identifiers", tags=["identifiers"])


class InstrumentSummary(BaseModel):
    id: str
    vt_symbol: str
    ticker: str
    exchange: str | None = None
    asset_class: str | None = None
    security_type: str | None = None
    sector: str | None = None
    industry: str | None = None
    region: str | None = None
    currency: str | None = None


class IdentifierRecord(BaseModel):
    id: str
    scheme: str
    value: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_id: str | None = None
    confidence: float = 1.0
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class InstrumentGraph(BaseModel):
    instrument: InstrumentSummary
    identifiers: list[IdentifierRecord] = Field(default_factory=list)


class ResolveResponse(BaseModel):
    found: bool
    instrument: InstrumentSummary | None = None
    identifiers: list[IdentifierRecord] = Field(default_factory=list)


class RegisterLinkRequest(BaseModel):
    vt_symbol: str = Field(..., description="Existing instrument, e.g. AAPL.NASDAQ")
    scheme: str = Field(..., description="cik | cusip | isin | figi | lei | ...")
    value: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_name: str | None = None
    confidence: float = 1.0
    meta: dict[str, Any] = Field(default_factory=dict)


def _instrument_summary(row: Instrument) -> InstrumentSummary:
    return InstrumentSummary(
        id=row.id,
        vt_symbol=row.vt_symbol,
        ticker=row.ticker,
        exchange=row.exchange,
        asset_class=row.asset_class,
        security_type=row.security_type,
        sector=row.sector,
        industry=row.industry,
        region=row.region,
        currency=row.currency,
    )


@router.get("/resolve", response_model=ResolveResponse)
def resolve_identifier(
    scheme: str = Query(..., description="e.g. 'cik', 'ticker', 'isin'"),
    value: str = Query(..., description="Scheme-specific identifier value"),
    as_of: str | None = Query(default=None),
) -> ResolveResponse:
    as_of_dt = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(400, f"bad as_of: {exc}") from exc
    resolver = IdentifierResolver()
    inst = resolver.resolve_instrument(scheme, value, as_of=as_of_dt)
    if inst is None:
        return ResolveResponse(found=False)
    identifiers = [
        IdentifierRecord(**record)
        for record in resolver.instrument_identifiers(inst.id)
    ]
    return ResolveResponse(
        found=True,
        instrument=_instrument_summary(inst),
        identifiers=identifiers,
    )


@router.get("/instrument/{vt_symbol}", response_model=InstrumentGraph)
def instrument_graph(vt_symbol: str) -> InstrumentGraph:
    with get_session() as session:
        row = session.execute(
            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, f"instrument {vt_symbol!r} not found")
        summary = _instrument_summary(row)
    identifiers = [
        IdentifierRecord(**record)
        for record in IdentifierResolver().instrument_identifiers(summary.id)
    ]
    return InstrumentGraph(instrument=summary, identifiers=identifiers)


@router.post("/link", response_model=list[str])
def register_link(req: RegisterLinkRequest) -> list[str]:
    """Manually register a ``(scheme, value)`` alias for an instrument."""
    from aqp.data.sources.base import IdentifierSpec

    resolver = IdentifierResolver(source_name=req.source_name)
    spec = IdentifierSpec(
        scheme=req.scheme,
        value=req.value,
        entity_kind="instrument",
        instrument_vt_symbol=req.vt_symbol,
        valid_from=req.valid_from,
        valid_to=req.valid_to,
        confidence=float(req.confidence),
        meta=dict(req.meta or {}),
    )
    return resolver.upsert_links([spec])
