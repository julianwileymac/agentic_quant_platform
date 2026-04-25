"""Knowledge-graph entity browsing endpoints.

Surfaces the full corporate-entity graph stored in
:mod:`aqp.persistence.models_entities` so the Data Browser can render
issuer detail, ownership, key-executives, locations, sector / industry
classifications, and a small relationship-graph traversal.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select

from aqp.persistence.db import get_session
from aqp.persistence.models import Instrument
from aqp.persistence.models_entities import (
    EntityRelationship,
    ExecutiveCompensation,
    Industry,
    IndustryClassification,
    Issuer,
    KeyExecutive,
    Location,
    Sector,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entities", tags=["entities"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IssuerSummary(BaseModel):
    id: str
    name: str
    legal_name: str | None = None
    kind: str
    cik: str | None = None
    lei: str | None = None
    cusip: str | None = None
    isin: str | None = None
    figi: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str | None = None
    entity_status: str | None = None


class IssuerDetail(IssuerSummary):
    classifications: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    executives: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    instruments: list[dict[str, Any]] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    from_id: str
    to_id: str
    relationship_type: str
    ownership_pct: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphPayload(BaseModel):
    root_id: str
    depth: int
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _issuer_to_summary(row: Issuer) -> IssuerSummary:
    return IssuerSummary(
        id=row.id,
        name=row.name,
        legal_name=row.legal_name,
        kind=row.kind,
        cik=row.cik,
        lei=row.lei,
        cusip=row.cusip,
        isin=row.isin,
        figi=row.figi,
        sector=getattr(row, "sector", None),
        industry=getattr(row, "industry", None),
        country=getattr(row, "country", None),
        currency=getattr(row, "currency", None),
        entity_status=row.entity_status,
    )


# ---------------------------------------------------------------------------
# Issuer endpoints
# ---------------------------------------------------------------------------


@router.get("/issuers", response_model=list[IssuerSummary])
def list_issuers(
    kind: str | None = None,
    q: str | None = None,
    sector: str | None = None,
    country: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[IssuerSummary]:
    with get_session() as session:
        stmt = select(Issuer).order_by(Issuer.name).limit(limit).offset(offset)
        if kind:
            stmt = stmt.where(Issuer.kind == kind)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Issuer.name.ilike(like), Issuer.legal_name.ilike(like)))
        rows = session.execute(stmt).scalars().all()
        out = [_issuer_to_summary(r) for r in rows]
    if sector:
        out = [r for r in out if (r.sector or "").lower() == sector.lower()]
    if country:
        out = [r for r in out if (r.country or "").lower() == country.lower()]
    return out


@router.get("/issuers/{issuer_id}", response_model=IssuerDetail)
def get_issuer(issuer_id: str) -> IssuerDetail:
    with get_session() as session:
        issuer = session.get(Issuer, issuer_id)
        if issuer is None:
            raise HTTPException(404, f"no issuer {issuer_id}")
        cls_rows = session.execute(
            select(IndustryClassification).where(
                IndustryClassification.issuer_id == issuer_id
            )
        ).scalars().all()
        loc_rows = session.execute(
            select(Location).where(Location.issuer_id == issuer_id)
        ).scalars().all()
        exec_rows = session.execute(
            select(KeyExecutive).where(KeyExecutive.issuer_id == issuer_id).limit(50)
        ).scalars().all()
        rels = session.execute(
            select(EntityRelationship).where(
                or_(
                    EntityRelationship.from_entity_id == issuer_id,
                    EntityRelationship.to_entity_id == issuer_id,
                )
            ).limit(200)
        ).scalars().all()
        instruments = session.execute(
            select(Instrument).where(Instrument.issuer_id == issuer_id).limit(200)
        ).scalars().all()

        summary = _issuer_to_summary(issuer)
        return IssuerDetail(
            **summary.model_dump(),
            classifications=[
                {
                    "scheme": c.scheme,
                    "code": c.code,
                    "label": c.label,
                    "level": c.level,
                    "parent_code": c.parent_code,
                }
                for c in cls_rows
            ],
            locations=[
                {
                    "country": l.country,
                    "country_iso": l.country_iso,
                    "region": l.region,
                    "state": l.state,
                    "city": l.city,
                    "is_headquarters": bool(l.is_headquarters),
                }
                for l in loc_rows
            ],
            executives=[
                {
                    "name": e.name,
                    "title": e.title,
                    "tenure_start": str(e.tenure_start) if e.tenure_start else None,
                    "tenure_end": str(e.tenure_end) if e.tenure_end else None,
                    "compensation": e.compensation,
                    "fiscal_year": e.fiscal_year,
                }
                for e in exec_rows
            ],
            relationships=[
                {
                    "from_kind": r.from_kind,
                    "from_entity_id": r.from_entity_id,
                    "to_kind": r.to_kind,
                    "to_entity_id": r.to_entity_id,
                    "relationship_type": r.relationship_type,
                    "ownership_pct": r.ownership_pct,
                    "valid_from": str(r.valid_from) if r.valid_from else None,
                    "valid_to": str(r.valid_to) if r.valid_to else None,
                    "source": r.source,
                }
                for r in rels
            ],
            instruments=[
                {
                    "id": i.id,
                    "vt_symbol": i.vt_symbol,
                    "ticker": i.ticker,
                    "exchange": i.exchange,
                    "asset_class": getattr(i, "asset_class", None),
                    "security_type": getattr(i, "security_type", None),
                    "is_active": bool(getattr(i, "is_active", True)),
                }
                for i in instruments
            ],
        )


@router.get("/issuers/{issuer_id}/relationships")
def get_relationships(issuer_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(
            select(EntityRelationship)
            .where(
                or_(
                    EntityRelationship.from_entity_id == issuer_id,
                    EntityRelationship.to_entity_id == issuer_id,
                )
            )
            .order_by(desc(EntityRelationship.created_at))
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "from_kind": r.from_kind,
                "from_entity_id": r.from_entity_id,
                "to_kind": r.to_kind,
                "to_entity_id": r.to_entity_id,
                "relationship_type": r.relationship_type,
                "ownership_pct": r.ownership_pct,
                "valid_from": str(r.valid_from) if r.valid_from else None,
                "valid_to": str(r.valid_to) if r.valid_to else None,
                "source": r.source,
            }
            for r in rows
        ]


@router.get("/issuers/{issuer_id}/instruments")
def get_instruments(issuer_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.execute(
            select(Instrument).where(Instrument.issuer_id == issuer_id).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "vt_symbol": r.vt_symbol,
                "ticker": r.ticker,
                "exchange": r.exchange,
                "asset_class": getattr(r, "asset_class", None),
                "security_type": getattr(r, "security_type", None),
                "is_active": bool(getattr(r, "is_active", True)),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Sector / industry catalogs
# ---------------------------------------------------------------------------


@router.get("/sectors")
def list_sectors(scheme: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(Sector).order_by(Sector.name).limit(limit)
        if scheme:
            stmt = stmt.where(Sector.scheme == scheme)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "scheme": r.scheme,
                "code": r.code,
                "name": r.name,
                "level": r.level,
                "parent_id": r.parent_id,
            }
            for r in rows
        ]


@router.get("/industries")
def list_industries(
    scheme: str | None = None,
    sector_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(Industry).order_by(Industry.name).limit(limit)
        if scheme:
            stmt = stmt.where(Industry.scheme == scheme)
        if sector_id:
            stmt = stmt.where(Industry.sector_id == sector_id)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "scheme": r.scheme,
                "code": r.code,
                "name": r.name,
                "sector_id": r.sector_id,
                "level": r.level,
                "parent_id": r.parent_id,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Ownership endpoint (13F + insider) — graceful when ownership module absent.
# ---------------------------------------------------------------------------


@router.get("/issuers/{issuer_id}/ownership")
def get_ownership(issuer_id: str, limit: int = 200) -> dict[str, Any]:
    """Return institutional 13F holdings + insider transactions, if available."""
    holdings: list[dict[str, Any]] = []
    insider: list[dict[str, Any]] = []
    try:
        from aqp.persistence import models_ownership  # type: ignore[import]

        Holding = getattr(models_ownership, "InstitutionalHolding", None)
        InsiderTx = getattr(models_ownership, "InsiderTransaction", None)
        with get_session() as session:
            if Holding is not None:
                rows = session.execute(
                    select(Holding).where(Holding.issuer_id == issuer_id).limit(limit)
                ).scalars().all()
                holdings = [
                    {k: v for k, v in vars(r).items() if not k.startswith("_")}
                    for r in rows
                ]
            if InsiderTx is not None:
                rows = session.execute(
                    select(InsiderTx).where(InsiderTx.issuer_id == issuer_id).limit(limit)
                ).scalars().all()
                insider = [
                    {k: v for k, v in vars(r).items() if not k.startswith("_")}
                    for r in rows
                ]
    except Exception:
        logger.info("ownership module not available", exc_info=True)
    return {"holdings": holdings, "insider": insider}


# ---------------------------------------------------------------------------
# Events endpoint — graceful when events module absent.
# ---------------------------------------------------------------------------


@router.get("/issuers/{issuer_id}/events")
def get_events(issuer_id: str, limit: int = 200) -> list[dict[str, Any]]:
    try:
        from aqp.persistence import models_events  # type: ignore[import]

        EventCls = (
            getattr(models_events, "CalendarEvent", None)
            or getattr(models_events, "CorporateEvent", None)
        )
        if EventCls is None:
            return []
        with get_session() as session:
            rows = session.execute(
                select(EventCls).where(EventCls.issuer_id == issuer_id).limit(limit)
            ).scalars().all()
        return [
            {k: v for k, v in vars(r).items() if not k.startswith("_")}
            for r in rows
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------


@router.get("/graph", response_model=GraphPayload)
def issuer_graph(
    root_id: str,
    depth: int = Query(default=1, ge=0, le=3),
    max_nodes: int = Query(default=100, le=500),
) -> GraphPayload:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    frontier: set[str] = {root_id}
    visited: set[str] = set()
    with get_session() as session:
        for _ in range(depth + 1):
            if not frontier:
                break
            current = list(frontier)
            frontier = set()
            issuer_rows = session.execute(
                select(Issuer).where(Issuer.id.in_(current))
            ).scalars().all()
            for r in issuer_rows:
                if r.id not in nodes:
                    nodes[r.id] = GraphNode(
                        id=r.id,
                        label=r.name,
                        kind=r.kind,
                        meta={
                            "sector_id": getattr(r, "sector_id", None),
                            "country": getattr(r, "country", None),
                        },
                    )
            visited.update(current)
            if len(nodes) >= max_nodes:
                break
            rel_rows = session.execute(
                select(EntityRelationship).where(
                    or_(
                        EntityRelationship.from_entity_id.in_(current),
                        EntityRelationship.to_entity_id.in_(current),
                    )
                )
            ).scalars().all()
            for r in rel_rows:
                edges.append(
                    GraphEdge(
                        from_id=r.from_entity_id,
                        to_id=r.to_entity_id,
                        relationship_type=r.relationship_type,
                        ownership_pct=r.ownership_pct,
                        meta={"valid_from": str(r.valid_from) if r.valid_from else None},
                    )
                )
                for nid in (r.from_entity_id, r.to_entity_id):
                    if nid not in visited:
                        frontier.add(nid)
                if len(nodes) >= max_nodes:
                    break
    return GraphPayload(
        root_id=root_id,
        depth=depth,
        nodes=list(nodes.values()),
        edges=edges,
    )
