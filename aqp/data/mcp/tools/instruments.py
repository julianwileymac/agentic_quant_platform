"""Instrument-level DataMCP tools.

Exposes read-only tools over the extended Phase 1 instrument taxonomy
and the ``instrument_measures`` registry:

* ``data.instruments.measures`` -- list available metrics for an
  instrument (measure_type, frequency, source dataset, dataset_field)
* ``data.instruments.depositary_receipts`` -- ADR/GDR depositary-receipt
  metadata + underlying linkage for cross-market arbitrage prep
* ``data.instruments.reit_portfolio`` -- REIT property-portfolio
  composition for sector-rotation strategies
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.instruments.measures
# ---------------------------------------------------------------------------


class InstrumentMeasuresInput(BaseModel):
    """Input schema for ``data.instruments.measures``."""

    vt_symbol: str | None = Field(
        default=None, description="Resolve by vt_symbol (e.g. 'AAPL.NASDAQ')."
    )
    instrument_id: str | None = Field(
        default=None, description="Resolve by direct instrument id (UUID)."
    )
    measure_type: str | None = Field(
        default=None,
        description=(
            "Optional filter on measure_type (price | volume | implied_volatility | "
            "ffo | distribution | greek_delta | basis | ...)."
        ),
    )
    frequency: str | None = Field(
        default=None,
        description=(
            "Optional filter on frequency (tick | minute | day | week | ...)."
        ),
    )
    active_only: bool = Field(
        default=True,
        description="When True, hide rows where ``is_active=False``.",
    )


@register_data_mcp_tool
class InstrumentMeasuresTool(DataMCPTool):
    """List available metrics for an instrument.

    The registry table is the single answer to "what data exists for
    AAPL?" -- agents query this BEFORE drafting an Iceberg / SQL query
    so they don't select a column that doesn't exist for the
    instrument-frequency pair they care about.
    """

    name = "data.instruments.measures"
    description = (
        "List the measurable quantities available for an instrument. "
        "Each row carries measure_type (price / volume / implied_vol / "
        "ffo / etc.), frequency (tick / day / month), the dataset that "
        "carries it, and the column name in that dataset. Use this "
        "BEFORE issuing a data query so you select an actually-present "
        "column."
    )
    args_schema = InstrumentMeasuresInput
    category = "instruments"
    tags = ("instruments", "measures", "metadata")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        vt_symbol: str | None = None,
        instrument_id: str | None = None,
        measure_type: str | None = None,
        frequency: str | None = None,
        active_only: bool = True,
    ) -> MCPToolResult:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import Instrument
        from aqp.persistence.models_instruments import InstrumentMeasure

        with get_session() as session:
            resolved_id = instrument_id
            if resolved_id is None and vt_symbol:
                resolved_id = session.execute(
                    select(Instrument.id).where(Instrument.vt_symbol == vt_symbol)
                ).scalar_one_or_none()
            if resolved_id is None:
                return MCPToolResult(
                    ok=False,
                    error="must provide vt_symbol or instrument_id; "
                    "vt_symbol must match an existing row",
                )
            stmt = select(InstrumentMeasure).where(
                InstrumentMeasure.instrument_id == resolved_id
            )
            if measure_type:
                stmt = stmt.where(
                    InstrumentMeasure.measure_type == measure_type.strip().lower()
                )
            if frequency:
                stmt = stmt.where(
                    InstrumentMeasure.frequency == frequency.strip().lower()
                )
            if active_only:
                stmt = stmt.where(InstrumentMeasure.is_active.is_(True))
            stmt = stmt.order_by(
                InstrumentMeasure.measure_type.asc(),
                InstrumentMeasure.frequency.asc(),
            )
            rows = session.execute(stmt).scalars().all()
            out = [
                {
                    "instrument_id": r.instrument_id,
                    "measure_type": r.measure_type,
                    "frequency": r.frequency,
                    "dataset_field": r.dataset_field,
                    "source_dataset_id": r.source_dataset_id,
                    "unit": r.unit,
                    "description": r.description,
                    "first_available": (
                        r.first_available.isoformat() if r.first_available else None
                    ),
                    "last_available": (
                        r.last_available.isoformat() if r.last_available else None
                    ),
                    "is_active": bool(r.is_active),
                    "meta": dict(r.meta or {}),
                }
                for r in rows
            ]
        return MCPToolResult(
            ok=True,
            data=out,
            rows_returned=len(out),
            summary=(
                f"{len(out)} measures for {vt_symbol or resolved_id}"
                + (f" (measure={measure_type})" if measure_type else "")
                + (f" (freq={frequency})" if frequency else "")
            ),
        )


# ---------------------------------------------------------------------------
# data.instruments.depositary_receipts
# ---------------------------------------------------------------------------


class DepositaryReceiptsInput(BaseModel):
    """Input schema for ``data.instruments.depositary_receipts``."""

    underlying_isin: str | None = Field(
        default=None,
        description="Filter by underlying foreign equity ISIN.",
    )
    receipt_kind: Literal["adr", "gdr", "any"] = Field(
        default="any",
        description="Restrict to ADRs only, GDRs only, or return both.",
    )
    sponsorship_level: str | None = Field(
        default=None,
        description="ADR only: I | II | III | 144A | Reg_S | unsponsored",
    )
    listing_venue: str | None = Field(
        default=None,
        description="Filter by listing venue (NYSE / LSE / LuxSE / Frankfurt / ...).",
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class DepositaryReceiptsTool(DataMCPTool):
    """List ADR / GDR rows with their underlying-equity FK.

    The cross-market basis algorithm uses this tool to discover ADR /
    GDR pairs whose underlying lives in a known foreign market. Each
    row carries the conversion_ratio + depository bank, so the agent
    can compute implied prices without an extra join.
    """

    name = "data.instruments.depositary_receipts"
    description = (
        "List ADRs / GDRs with their underlying foreign-equity linkage. "
        "Each row carries conversion_ratio, depository bank, "
        "sponsorship level (ADR) or regulatory regime (GDR), and the "
        "FK to the underlying instrument row. Use this to discover "
        "cross-market arbitrage candidates (e.g. BABA NYSE ADR vs HKEX "
        "9988 common)."
    )
    args_schema = DepositaryReceiptsInput
    category = "instruments"
    tags = ("instruments", "adr", "gdr", "cross_market")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        underlying_isin: str | None = None,
        receipt_kind: str = "any",
        sponsorship_level: str | None = None,
        listing_venue: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import Instrument
        from aqp.persistence.models_instruments import InstrumentADR, InstrumentGDR

        out: list[dict[str, Any]] = []
        with get_session() as session:
            if receipt_kind in ("any", "adr"):
                stmt_adr = (
                    select(InstrumentADR, Instrument)
                    .join(Instrument, Instrument.id == InstrumentADR.id)
                )
                if underlying_isin:
                    stmt_adr = stmt_adr.where(
                        InstrumentADR.underlying_isin == underlying_isin
                    )
                if sponsorship_level:
                    stmt_adr = stmt_adr.where(
                        InstrumentADR.sponsorship_level == sponsorship_level
                    )
                if listing_venue:
                    stmt_adr = stmt_adr.where(
                        InstrumentADR.listing_venue == listing_venue
                    )
                stmt_adr = stmt_adr.limit(int(limit))
                for adr, inst in session.execute(stmt_adr).all():
                    out.append(
                        {
                            "kind": "adr",
                            "id": adr.id,
                            "vt_symbol": inst.vt_symbol,
                            "ticker": inst.ticker,
                            "underlying_instrument_id": adr.underlying_instrument_id,
                            "underlying_ticker": adr.underlying_ticker,
                            "underlying_venue": adr.underlying_venue,
                            "underlying_isin": adr.underlying_isin,
                            "conversion_ratio": (
                                float(adr.conversion_ratio)
                                if adr.conversion_ratio is not None
                                else None
                            ),
                            "depository_bank_name": adr.depository_bank_name,
                            "sponsorship_level": adr.sponsorship_level,
                            "listing_venue": adr.listing_venue,
                            "isin": adr.isin,
                        }
                    )
            if receipt_kind in ("any", "gdr"):
                stmt_gdr = (
                    select(InstrumentGDR, Instrument)
                    .join(Instrument, Instrument.id == InstrumentGDR.id)
                )
                if underlying_isin:
                    stmt_gdr = stmt_gdr.where(
                        InstrumentGDR.underlying_isin == underlying_isin
                    )
                if listing_venue:
                    stmt_gdr = stmt_gdr.where(
                        InstrumentGDR.listing_venue == listing_venue
                    )
                stmt_gdr = stmt_gdr.limit(int(limit))
                for gdr, inst in session.execute(stmt_gdr).all():
                    out.append(
                        {
                            "kind": "gdr",
                            "id": gdr.id,
                            "vt_symbol": inst.vt_symbol,
                            "ticker": inst.ticker,
                            "underlying_instrument_id": gdr.underlying_instrument_id,
                            "underlying_ticker": gdr.underlying_ticker,
                            "underlying_venue": gdr.underlying_venue,
                            "underlying_isin": gdr.underlying_isin,
                            "conversion_ratio": (
                                float(gdr.conversion_ratio)
                                if gdr.conversion_ratio is not None
                                else None
                            ),
                            "depository_bank_name": gdr.depository_bank_name,
                            "regulatory_regime": gdr.regulatory_regime,
                            "listing_venue": gdr.listing_venue,
                            "isin": gdr.isin,
                        }
                    )
        return MCPToolResult(
            ok=True,
            data=out[: int(limit)],
            rows_returned=len(out),
            summary=f"{len(out)} depositary receipts",
        )


# ---------------------------------------------------------------------------
# data.instruments.reit_portfolio
# ---------------------------------------------------------------------------


class ReitPortfolioInput(BaseModel):
    """Input schema for ``data.instruments.reit_portfolio``."""

    vt_symbol: str | None = Field(
        default=None, description="Resolve REIT by vt_symbol."
    )
    instrument_id: str | None = Field(
        default=None, description="Resolve REIT by direct instrument id."
    )
    property_sector: str | None = Field(
        default=None,
        description=(
            "Filter REITs by property sector (residential | commercial | "
            "industrial | healthcare | data_center | retail | hospitality | "
            "diversified | infrastructure | timber)."
        ),
    )
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ReitPortfolioTool(DataMCPTool):
    """Return REIT property-portfolio composition + key fundamentals.

    Agents use this for sector-rotation strategies that need to know
    "what's in this REIT?" -- the property portfolio composition drives
    the residual sensitivity to a given macro factor (rates,
    occupancy, hospitality volume, etc.). Each row carries FFO,
    distribution yield, payout ratio, and debt-to-equity for the LLM
    to reason about.
    """

    name = "data.instruments.reit_portfolio"
    description = (
        "Return REIT property-portfolio composition + FFO / distribution "
        "yield / payout ratio / debt-to-equity. Use this for sector-rotation "
        "strategies that need to know what's actually inside a REIT before "
        "computing residual factor exposures."
    )
    args_schema = ReitPortfolioInput
    category = "instruments"
    tags = ("instruments", "reit", "real_estate")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        vt_symbol: str | None = None,
        instrument_id: str | None = None,
        property_sector: str | None = None,
        limit: int = 25,
    ) -> MCPToolResult:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import Instrument
        from aqp.persistence.models_instruments import InstrumentREIT

        out: list[dict[str, Any]] = []
        with get_session() as session:
            stmt = (
                select(InstrumentREIT, Instrument)
                .join(Instrument, Instrument.id == InstrumentREIT.id)
            )
            if vt_symbol:
                stmt = stmt.where(Instrument.vt_symbol == vt_symbol)
            if instrument_id:
                stmt = stmt.where(Instrument.id == instrument_id)
            if property_sector:
                stmt = stmt.where(
                    InstrumentREIT.property_sector == property_sector.strip().lower()
                )
            stmt = stmt.limit(int(limit))
            for reit, inst in session.execute(stmt).all():
                out.append(
                    {
                        "id": reit.id,
                        "vt_symbol": inst.vt_symbol,
                        "ticker": inst.ticker,
                        "reit_class": reit.reit_class,
                        "property_sector": reit.property_sector,
                        "property_portfolio": list(reit.property_portfolio_json or []),
                        "distribution_yield": (
                            float(reit.distribution_yield)
                            if reit.distribution_yield is not None
                            else None
                        ),
                        "ffo_per_share": (
                            float(reit.ffo_per_share)
                            if reit.ffo_per_share is not None
                            else None
                        ),
                        "payout_ratio": (
                            float(reit.payout_ratio)
                            if reit.payout_ratio is not None
                            else None
                        ),
                        "debt_to_equity": (
                            float(reit.debt_to_equity)
                            if reit.debt_to_equity is not None
                            else None
                        ),
                        "country": reit.country,
                    }
                )
        return MCPToolResult(
            ok=True,
            data=out,
            rows_returned=len(out),
            summary=f"{len(out)} REIT rows",
        )


__all__ = [
    "DepositaryReceiptsTool",
    "InstrumentMeasuresTool",
    "ReitPortfolioTool",
]
