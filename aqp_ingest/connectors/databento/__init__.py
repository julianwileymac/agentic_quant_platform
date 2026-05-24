"""Databento connectors.

Databento ships a binary protocol and a Python SDK (``databento``).
The historical endpoint is REST-ish, but the live endpoint is a
gRPC stream. The :class:`DatabentoHistoricalStream` here uses the
HTTP surface so it composes with our :class:`RateLimitedHttpStream`
base; the live path will be a separate gRPC adapter in Phase 2.
"""
from __future__ import annotations

from aqp_ingest.connectors.databento.historical import DatabentoHistoricalStream

__all__ = ["DatabentoHistoricalStream"]
