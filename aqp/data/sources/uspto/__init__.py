"""USPTO adapter (PatentsView for patents, TSDR for trademarks, PEDS for assignments)."""
from __future__ import annotations

from aqp.data.sources.uspto.assignments import UsptoAssignmentsAdapter
from aqp.data.sources.uspto.catalog import (
    upsert_uspto_assignment,
    upsert_uspto_patent,
    upsert_uspto_trademark,
)
from aqp.data.sources.uspto.client import UsptoClient, UsptoClientError
from aqp.data.sources.uspto.patents import UsptoPatentsAdapter
from aqp.data.sources.uspto.trademarks import UsptoTrademarksAdapter

__all__ = [
    "UsptoAssignmentsAdapter",
    "UsptoClient",
    "UsptoClientError",
    "UsptoPatentsAdapter",
    "UsptoTrademarksAdapter",
    "upsert_uspto_assignment",
    "upsert_uspto_patent",
    "upsert_uspto_trademark",
]
