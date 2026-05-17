"""Continuous futures-curve DataMCP tools.

Exposes :mod:`aqp.data.futures.curve` as agent-callable tools:

* ``data.futures.curve.list`` -- coarse catalog of every known curve
* ``data.futures.curve.stitched`` -- stitched continuous series with a
  chosen roll rule and adjustment mode

Both tools are read-only; persistence of the stitched series back to
Iceberg is left to the analysis-flow path so agents can't accidentally
write gold-tier data without going through the proper runtime.
"""
from __future__ import annotations

import logging
from datetime import date as dateType
from typing import Any, Literal

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.futures.curve.list
# ---------------------------------------------------------------------------


class ListFuturesCurvesInput(BaseModel):
    """Input schema for ``data.futures.curve.list``."""

    root_symbol: str | None = Field(
        default=None,
        description=(
            "Optional substring filter on root symbol (e.g. 'ES' returns "
            "every ES-family curve). Omit to list every curve."
        ),
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class ListFuturesCurvesTool(DataMCPTool):
    """List every known futures curve with coverage metadata."""

    name = "data.futures.curve.list"
    description = (
        "List every continuous futures curve known to the platform. "
        "Each row carries the root symbol (ES, NQ, CL, ZN, ...), the "
        "snapshot-date coverage window, and the contract-expiry range. "
        "Use this to discover which roll-stitched series are available "
        "before requesting one via data.futures.curve.stitched."
    )
    args_schema = ListFuturesCurvesInput
    category = "futures"
    tags = ("futures", "curve", "catalog")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        root_symbol: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.data.futures.curve import list_curves

        rows = list_curves()
        if root_symbol:
            needle = root_symbol.strip().upper()
            rows = [r for r in rows if needle in r["root_symbol"].upper()]
        rows = rows[: int(limit)]
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"{len(rows)} futures curves",
        )


# ---------------------------------------------------------------------------
# data.futures.curve.stitched
# ---------------------------------------------------------------------------


class StitchedFuturesCurveInput(BaseModel):
    """Input schema for ``data.futures.curve.stitched``."""

    root_symbol: str = Field(description="Root symbol of the curve (ES, NQ, CL, ZN, ...).")
    rule: Literal["volume", "date", "open_interest"] = Field(
        default="volume",
        description="Roll rule strategy.",
    )
    adjustment: Literal["none", "back_adjusted", "ratio"] = Field(
        default="back_adjusted",
        description="Roll-adjustment mode.",
    )
    days_before_expiry: int = Field(
        default=5,
        ge=0,
        le=30,
        description="Used only when ``rule=='date'``.",
    )
    min_volume_ratio: float = Field(
        default=1.0,
        ge=0.0,
        description="Used only when ``rule=='volume'``.",
    )
    start_date: dateType | None = Field(default=None)
    end_date: dateType | None = Field(default=None)
    limit_rows: int = Field(
        default=2000,
        ge=1,
        le=20_000,
        description="Max number of rows returned (most-recent first).",
    )


@register_data_mcp_tool
class StitchedFuturesCurveTool(DataMCPTool):
    """Return a roll-stitched continuous futures series.

    The series is rebuilt from the per-snapshot rows in
    ``futures_curves`` using the requested roll rule and adjustment
    mode. The tool emits both the stitched rows and the audit list of
    roll transitions so the agent can spot bad rolls (large adjustment
    jumps).
    """

    name = "data.futures.curve.stitched"
    description = (
        "Build a roll-stitched continuous futures series. Pick the roll "
        "rule (volume / date / open_interest) and the adjustment mode "
        "(back_adjusted / ratio / none). Returns the per-day stitched "
        "rows + an audit log of roll transitions. The default "
        "back_adjusted mode is what most CTA-style models expect."
    )
    args_schema = StitchedFuturesCurveInput
    category = "futures"
    tags = ("futures", "curve", "stitch", "roll")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        root_symbol: str,
        rule: str = "volume",
        adjustment: str = "back_adjusted",
        days_before_expiry: int = 5,
        min_volume_ratio: float = 1.0,
        start_date: dateType | None = None,
        end_date: dateType | None = None,
        limit_rows: int = 2000,
    ) -> MCPToolResult:
        from aqp.data.futures.curve import (
            DateBasedRoll,
            OpenInterestRoll,
            VolumeBasedRoll,
            load_curve_snapshots,
            stitch_curve,
        )

        curve = load_curve_snapshots(
            root_symbol, start_date=start_date, end_date=end_date
        )
        if not curve.snapshots:
            return MCPToolResult(
                ok=True,
                data={"rows": [], "rolls": []},
                rows_returned=0,
                summary=f"no snapshots for {root_symbol}",
            )

        if rule == "volume":
            roll_rule: Any = VolumeBasedRoll(min_volume_ratio=float(min_volume_ratio))
        elif rule == "date":
            roll_rule = DateBasedRoll(days_before_expiry=int(days_before_expiry))
        elif rule == "open_interest":
            roll_rule = OpenInterestRoll(min_oi_ratio=float(min_volume_ratio))
        else:
            return MCPToolResult(ok=False, error=f"unknown roll rule {rule!r}")

        rows, rolls = stitch_curve(curve, rule=roll_rule, adjustment=adjustment)  # type: ignore[arg-type]
        # Most-recent-first cap so MCP payloads stay bounded.
        rows = list(reversed(rows))[: int(limit_rows)]
        out_rows = [
            {
                "snapshot_date": r.snapshot_date.isoformat(),
                "price": r.price,
                "raw_price": r.raw_price,
                "contract_symbol": r.contract_symbol,
                "contract_expiry": r.contract_expiry.isoformat(),
                "adjustment_factor": r.adjustment_factor,
                "rolled": bool(r.rolled),
            }
            for r in rows
        ]
        out_rolls = [
            {
                "snapshot_date": e.snapshot_date.isoformat(),
                "from_contract": e.from_contract,
                "from_expiry": e.from_expiry.isoformat(),
                "to_contract": e.to_contract,
                "to_expiry": e.to_expiry.isoformat(),
                "rule_name": e.rule_name,
                "from_price": e.from_price,
                "to_price": e.to_price,
            }
            for e in rolls
        ]
        return MCPToolResult(
            ok=True,
            data={
                "root_symbol": root_symbol,
                "rule": rule,
                "adjustment": adjustment,
                "rows": out_rows,
                "rolls": out_rolls,
            },
            rows_returned=len(out_rows),
            summary=(
                f"{root_symbol}: {len(out_rows)} stitched rows, "
                f"{len(out_rolls)} roll events ({rule}/{adjustment})"
            ),
        )


__all__ = [
    "ListFuturesCurvesTool",
    "StitchedFuturesCurveTool",
]
