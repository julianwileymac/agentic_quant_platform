"""Temporal identifier resolver service.

This package owns the canonical mapping between an entity (instrument,
issuer, GDelt theme, FRED series) and the various scheme/value
identifiers known for it across time. The legacy
``Instrument.identifiers`` JSON blob is kept for back-compat, but new
readers (Phase 1+) MUST go through :class:`IdentifierResolver` so
``as_of`` lookups walk the time-versioned ``identifier_links`` rows
instead of the flat blob.

The :func:`resolve` and :func:`history` helpers are exposed as
:class:`DataMCPTool` subclasses under
:mod:`aqp.data.mcp.tools.identity` so agents can answer "what was
this CUSIP on 2018-06-12?" without an ORM import.
"""
from __future__ import annotations

from aqp.data.identity.resolver import (
    IdentifierHistoryRow,
    IdentifierResolution,
    IdentifierResolver,
    history,
    resolve,
    resolve_to_instrument,
)

__all__ = [
    "IdentifierHistoryRow",
    "IdentifierResolution",
    "IdentifierResolver",
    "history",
    "resolve",
    "resolve_to_instrument",
]
