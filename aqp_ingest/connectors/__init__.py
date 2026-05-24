"""Curated financial-API connectors.

Each subpackage hosts the streams for one vendor. Connectors
inherit from :class:`aqp_ingest_cdk.RateLimitedHttpStream` so the
per-(user, service, key_id) bucket is debited preemptively on
every outbound request.
"""
from __future__ import annotations
