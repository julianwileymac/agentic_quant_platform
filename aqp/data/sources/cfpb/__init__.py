"""CFPB Consumer Complaint Database adapter."""
from __future__ import annotations

from aqp.data.sources.cfpb.catalog import upsert_cfpb_complaint
from aqp.data.sources.cfpb.client import CfpbClient, CfpbClientError
from aqp.data.sources.cfpb.complaints import CFPB_COLUMNS, CfpbComplaintsAdapter

__all__ = [
    "CFPB_COLUMNS",
    "CfpbClient",
    "CfpbClientError",
    "CfpbComplaintsAdapter",
    "upsert_cfpb_complaint",
]
