"""Dedicated MCP server for the AQP MLOps surface.

The data-layer MCP server already exposes ``data.ml.*`` tools through
:mod:`aqp.data.mcp`. The dedicated ``aqp-ml-mcp`` server in this
subpackage publishes a **disjoint** canonical URI
(``settings.mcp_ml_canonical_uri``) so MCP clients that authenticate
specifically for the MLOps surface get audience-bound tokens. The
underlying tool catalog is the same ``data.ml.*`` subset; this server
just enforces the tighter audience binding (Hard Rule 49).

Routes published:

* FastAPI router at ``/mcp/ml`` (HTTP transport, mirrors ``/mcp/data``).
* Console script ``aqp-ml-mcp`` for the stdio transport.

The RFC 9728 metadata document lives at
``/.well-known/oauth-protected-resource/mcp/ml`` (added to
:mod:`aqp.api.well_known`).
"""
from __future__ import annotations

from aqp.ml_mcp.server import build_ml_mcp_router, run_stdio

__all__ = ["build_ml_mcp_router", "run_stdio"]
