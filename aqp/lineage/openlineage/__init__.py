"""OpenLineage relay (Workstream B).

Pure-additive relay of every :class:`LineageEvent` flowing through the
existing :class:`LineageBus` as an OpenLineage ``RunEvent`` POSTed to
Marquez. The transactional outbox pattern guarantees lineage events
commit alongside the data write — if the data transaction aborts,
neither the data row nor the outbox row makes it to Postgres.

Public surface:

- :func:`aqp_event_to_openlineage` — pure mapper from
  :class:`LineageEvent` to OpenLineage ``RunEvent`` dict.
- :class:`OpenLineageOutboxObserver` — :class:`BaseLineageObserver`
  that writes outbox rows.
- :func:`register_openlineage_observer` — idempotent boot helper.
- :func:`drain_outbox_once(limit)` — synchronous outbox-drain entry
  point used by the Celery beat task in
  :mod:`aqp.tasks.openlineage_relay_tasks`.
"""
from __future__ import annotations

from aqp.lineage.openlineage.mapper import (
    aqp_event_to_openlineage,
)
from aqp.lineage.openlineage.observer import (
    OpenLineageOutboxObserver,
    is_openlineage_relay_enabled,
    register_openlineage_observer,
    unregister_openlineage_observer,
)
from aqp.lineage.openlineage.relay import (
    drain_outbox_once,
    get_marquez_url,
    post_openlineage_event,
)

__all__ = [
    "OpenLineageOutboxObserver",
    "aqp_event_to_openlineage",
    "drain_outbox_once",
    "get_marquez_url",
    "is_openlineage_relay_enabled",
    "post_openlineage_event",
    "register_openlineage_observer",
    "unregister_openlineage_observer",
]
