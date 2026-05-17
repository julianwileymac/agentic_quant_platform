"""Identity-resolver DataMCP tools.

Exposes :class:`aqp.data.identity.resolver.IdentifierResolver` as
agent-callable :class:`DataMCPTool` subclasses so agents can answer
"what was AAPL's CUSIP on 2018-06-12?" or "walk every identifier
known for this instrument" without touching the ORM (AGENTS rule 22).

Two tools:

* ``data.identity.resolve`` -- forward ``(scheme, value, as_of)`` to a
  single best resolution
* ``data.identity.history`` -- walk every known alias for an entity
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.identity.resolve
# ---------------------------------------------------------------------------


class ResolveIdentifierInput(BaseModel):
    """Input schema for ``data.identity.resolve``."""

    scheme: Literal[
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
    ] = Field(description="Identifier scheme to resolve.")
    value: str = Field(description="Identifier value (case-preserved, trimmed).")
    as_of: datetime | None = Field(
        default=None,
        description="UTC timestamp for point-in-time resolution. Defaults to 'now'.",
    )
    entity_kind: str = Field(
        default="instrument",
        description="Entity-kind scope (instrument | fred_series | sec_filing | gdelt_theme | company).",
    )
    instrument_id: str | None = Field(
        default=None,
        description="Optional instrument-id scope when the caller already knows the parent.",
    )


@register_data_mcp_tool
class ResolveIdentifierTool(DataMCPTool):
    """Resolve a ``(scheme, value)`` pair to its identifier-row at ``as_of``.

    The tool walks the time-versioned ``identifier_links`` graph so the
    answer for "AAPL's CUSIP on 2018-06-12" is different from "AAPL's
    CUSIP right now" if a corporate action triggered a re-issue. Returns
    the validity window so the agent can decide whether the resolution
    is stable enough for a long-running backtest.
    """

    name = "data.identity.resolve"
    description = (
        "Resolve a financial identifier (CUSIP / ISIN / FIGI / ticker / "
        "SEDOL / LEI / etc.) to the underlying instrument or entity, "
        "honouring the validity window at ``as_of``. Use this BEFORE "
        "issuing any historical query that names an identifier so the "
        "backtest doesn't accidentally use a modern identifier on data "
        "the legacy identifier referred to."
    )
    args_schema = ResolveIdentifierInput
    category = "identity"
    tags = ("identity", "temporal", "resolver")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        # Identifier metadata is shared reference data — don't require a
        # workspace_id so cross-tenant tools can resolve too.
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        scheme: str,
        value: str,
        as_of: datetime | None = None,
        entity_kind: str = "instrument",
        instrument_id: str | None = None,
    ) -> MCPToolResult:
        from aqp.data.identity.resolver import resolve

        res = resolve(
            scheme=scheme,
            value=value,
            as_of=as_of,
            entity_kind=entity_kind,
            instrument_id=instrument_id,
        )
        if res is None:
            return MCPToolResult(
                ok=True,
                data=None,
                summary=f"no row for {scheme}={value!r} as of {as_of}",
            )
        return MCPToolResult(
            ok=True,
            data=res.to_json(),
            rows_returned=1,
            summary=(
                f"{scheme}={value!r} -> {res.entity_kind}:{res.entity_id} "
                f"(valid {res.valid_from or '-inf'}..{res.valid_to or '+inf'})"
            ),
        )


# ---------------------------------------------------------------------------
# data.identity.history
# ---------------------------------------------------------------------------


class IdentifierHistoryInput(BaseModel):
    """Input schema for ``data.identity.history``."""

    entity_kind: str = Field(
        default="instrument",
        description="Entity-kind scope (instrument | fred_series | sec_filing).",
    )
    entity_id: str = Field(
        description="Entity id (instrument UUID, FRED series id, filing id, ...).",
    )
    scheme: str | None = Field(
        default=None,
        description=(
            "Optional scheme filter (CUSIP / ISIN / ticker / ...). When omitted, "
            "all schemes are walked."
        ),
    )


@register_data_mcp_tool
class IdentifierHistoryTool(DataMCPTool):
    """Walk every identifier ever known for an entity.

    The history is sorted chronologically (open-start rows first,
    open-end rows last). Each row carries a confidence score so the
    agent can prefer canonical loader rows (``confidence=1.0``) over
    legacy JSON-blob backfills (``confidence=0.7``).
    """

    name = "data.identity.history"
    description = (
        "Walk the full identifier history for an entity. Returns every "
        "(scheme, value, valid_from, valid_to, confidence) tuple sorted "
        "chronologically. Use this when you suspect a ticker change "
        "(M&A, rebranding) might have happened in the backtest window."
    )
    args_schema = IdentifierHistoryInput
    category = "identity"
    tags = ("identity", "temporal", "audit")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        entity_kind: str,
        entity_id: str,
        scheme: str | None = None,
    ) -> MCPToolResult:
        from aqp.data.identity.resolver import history

        rows = history(entity_kind=entity_kind, entity_id=entity_id, scheme=scheme)
        return MCPToolResult(
            ok=True,
            data=[r.to_json() for r in rows],
            rows_returned=len(rows),
            summary=(
                f"{len(rows)} rows for {entity_kind}:{entity_id}"
                + (f" (scheme={scheme})" if scheme else "")
            ),
        )


__all__ = [
    "IdentifierHistoryTool",
    "ResolveIdentifierTool",
]
