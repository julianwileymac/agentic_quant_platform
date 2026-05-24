"""Active discovery surface — phase 1 of the self-service data fabric.

Unifies four sources into one browsable catalog: ingested
:class:`DatasetCatalog` rows, pending
:class:`SourceLibraryEntry` rows, Iceberg orphans (tables without a
Postgres row), and Airbyte connection inventory. Backs
``/discovery/*`` routes and the ``data.discovery.*`` DataMCPTools.

Public surface::

    from aqp.data.discovery import DiscoveryService, DiscoveryEntry

    svc = DiscoveryService()
    page = svc.list(lifecycle="pending", limit=50)

The narrative walkthrough is :file:`aqp_docs/data-discovery.md` and the
phase plan is
:file:`.cursor/plans/data-self-service-phase-1.plan.md`.
"""
from __future__ import annotations

from aqp.data.discovery.service import DiscoveryService
from aqp.data.discovery.types import DiscoveryEntry, DiscoveryLifecycleState

__all__ = [
    "DiscoveryEntry",
    "DiscoveryLifecycleState",
    "DiscoveryService",
]
