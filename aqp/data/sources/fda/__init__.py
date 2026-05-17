"""FDA openFDA adapter (drug/device applications, adverse events, recalls)."""
from __future__ import annotations

from aqp.data.sources.fda.adverse_events import FdaAdverseEventsAdapter
from aqp.data.sources.fda.applications import FdaApplicationsAdapter
from aqp.data.sources.fda.catalog import (
    upsert_fda_adverse_event,
    upsert_fda_application,
    upsert_fda_recall,
)
from aqp.data.sources.fda.client import FdaClient, FdaClientError
from aqp.data.sources.fda.recalls import FdaRecallsAdapter

__all__ = [
    "FdaAdverseEventsAdapter",
    "FdaApplicationsAdapter",
    "FdaClient",
    "FdaClientError",
    "FdaRecallsAdapter",
    "upsert_fda_adverse_event",
    "upsert_fda_application",
    "upsert_fda_recall",
]
