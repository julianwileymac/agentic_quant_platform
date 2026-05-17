"""Entity-centric DataMCP tools.

Wraps :mod:`aqp.data.products` so agents can pull pre-aggregated
context packs for one entity in a single call instead of stitching
together multiple raw catalog reads.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class LookupEquityEntityInput(BaseModel):
    vt_symbol: str = Field(..., description="Canonical vt_symbol eg. AAPL.NASDAQ.")
    bars_lookback_days: int = Field(default=30, ge=1, le=365)
    max_tokens: int | None = Field(default=4000, ge=200, le=64000)


@register_data_mcp_tool
class LookupEquityEntityTool(DataMCPTool):
    name = "data.entities.equity"
    description = (
        "Return a pre-aggregated EquityEntity context pack for one "
        "vt_symbol — instrument record, identifier links, fundamentals, "
        "ratios, news sentiment, regulatory mention counts, and recent "
        "bar snapshot."
    )
    args_schema = LookupEquityEntityInput
    category = "entities"
    tags = ("entities", "equity")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        vt_symbol: str,
        bars_lookback_days: int = 30,
        max_tokens: int | None = 4000,
    ) -> MCPToolResult:
        from aqp.data.products import EquityEntity

        product = EquityEntity(vt_symbol, bars_lookback_days=bars_lookback_days)
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"equity entity for {vt_symbol}",
        )


class LookupOptionChainInput(BaseModel):
    vt_symbol: str = Field(...)
    max_strikes: int = Field(default=50, ge=1, le=500)
    max_tokens: int | None = Field(default=4000, ge=200, le=64000)


@register_data_mcp_tool
class LookupOptionChainTool(DataMCPTool):
    name = "data.entities.option_chain"
    description = "Return the latest OptionChainSnapshot + chain series for an underlying vt_symbol."
    args_schema = LookupOptionChainInput
    category = "entities"
    tags = ("entities", "options")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        vt_symbol: str,
        max_strikes: int = 50,
        max_tokens: int | None = 4000,
    ) -> MCPToolResult:
        from aqp.data.products import OptionChainEntity

        product = OptionChainEntity(vt_symbol, max_strikes=max_strikes)
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"option chain for {vt_symbol}",
        )


class LookupPortfolioInput(BaseModel):
    portfolio_id: str = Field(...)
    recent_fills: int = Field(default=10, ge=1, le=100)
    max_tokens: int | None = Field(default=4000, ge=200, le=64000)


@register_data_mcp_tool
class LookupPortfolioTool(DataMCPTool):
    name = "data.entities.portfolio"
    description = (
        "Return a PortfolioEntity context pack — positions, recent "
        "fills, and the latest ledger snapshot."
    )
    args_schema = LookupPortfolioInput
    category = "entities"
    tags = ("entities", "portfolio")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        from aqp.data.mcp.policy import enforce_tenancy

        # Portfolios are tenant-scoped — never let an agent fish across
        # workspaces.
        enforce_tenancy(ctx)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        portfolio_id: str,
        recent_fills: int = 10,
        max_tokens: int | None = 4000,
    ) -> MCPToolResult:
        from aqp.data.products import PortfolioEntity

        product = PortfolioEntity(portfolio_id, recent_fills=recent_fills)
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"portfolio entity for {portfolio_id}",
        )


class LookupMacroSeriesInput(BaseModel):
    series_id: str = Field(..., description="Macro series identifier eg. FRED:DGS10.")
    recent_observations: int = Field(default=60, ge=1, le=600)
    max_tokens: int | None = Field(default=4000, ge=200, le=64000)


@register_data_mcp_tool
class LookupMacroSeriesTool(DataMCPTool):
    name = "data.entities.macro_series"
    description = "Return a MacroSeriesEntity for one FRED / BLS / Treasury series id."
    args_schema = LookupMacroSeriesInput
    category = "entities"
    tags = ("entities", "macro")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        series_id: str,
        recent_observations: int = 60,
        max_tokens: int | None = 4000,
    ) -> MCPToolResult:
        from aqp.data.products import MacroSeriesEntity

        product = MacroSeriesEntity(series_id, recent_observations=recent_observations)
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"macro series {series_id}",
        )


class LookupRegulatoryInput(BaseModel):
    vt_symbol: str = Field(...)
    per_table_limit: int = Field(default=10, ge=1, le=100)
    max_tokens: int | None = Field(default=4000, ge=200, le=64000)


@register_data_mcp_tool
class LookupRegulatoryEntityTool(DataMCPTool):
    name = "data.entities.regulatory"
    description = "Return a RegulatoryEntity (CFPB / FDA / USPTO mentions) for one vt_symbol."
    args_schema = LookupRegulatoryInput
    category = "entities"
    tags = ("entities", "regulatory")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        vt_symbol: str,
        per_table_limit: int = 10,
        max_tokens: int | None = 4000,
    ) -> MCPToolResult:
        from aqp.data.products import RegulatoryEntity

        product = RegulatoryEntity(vt_symbol, per_table_limit=per_table_limit)
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"regulatory entity for {vt_symbol}",
        )


class WalkInstrumentGraphInput(BaseModel):
    root_vt_symbol: str = Field(...)
    depth: int = Field(default=2, ge=1, le=5)
    max_nodes: int = Field(default=50, ge=1, le=500)
    max_tokens: int | None = Field(default=6000, ge=200, le=64000)


@register_data_mcp_tool
class WalkInstrumentGraphTool(DataMCPTool):
    name = "data.entities.instrument_graph"
    description = (
        "Walk the AQP entity graph rooted at one vt_symbol. Returns "
        "nodes (instruments / issuers) and edges (issuer_link / "
        "identifier_link) for the requested depth."
    )
    args_schema = WalkInstrumentGraphInput
    category = "entities"
    tags = ("entities", "graph")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        root_vt_symbol: str,
        depth: int = 2,
        max_nodes: int = 50,
        max_tokens: int | None = 6000,
    ) -> MCPToolResult:
        from aqp.data.products import InstrumentGraphProduct

        product = InstrumentGraphProduct(
            root_vt_symbol, depth=depth, max_nodes=max_nodes
        )
        return MCPToolResult(
            ok=True,
            data=product.to_context_pack(max_tokens=max_tokens),
            summary=f"instrument graph rooted at {root_vt_symbol}",
        )


__all__ = [
    "LookupEquityEntityTool",
    "LookupMacroSeriesTool",
    "LookupOptionChainTool",
    "LookupPortfolioTool",
    "LookupRegulatoryEntityTool",
    "WalkInstrumentGraphTool",
]
