"""Bloomberg BPIPE connector (binary BLPAPI protocol).

Per the BLPAPI Developer's Guide §6.7.1 we operate in Single-User
entitlement mode. The connector is a custom Python adapter (not a
RateLimitedHttpStream) because BPIPE speaks a binary, session-based
protocol — the rate limit is enforced at the SDK level via direct
:class:`aqp_ratelimit.RateLimitClient` calls before each
``ReferenceDataRequest`` / ``HistoricalDataRequest``.
"""
from __future__ import annotations

from aqp_ingest.connectors.bloomberg.bpipe import BloombergBpipeAdapter

__all__ = ["BloombergBpipeAdapter"]
