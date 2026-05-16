"""Celery tasks that drain the OwnershipEvent bus into the graph store.

Three tasks:

- :func:`drain_events` — pops up to ``ownership_sync_batch_size`` events
  off the Redis stream and applies them via
  :meth:`OwnershipGraphStore.apply_events`. Wired into Celery beat with
  a short interval (default 5s) so the projection lags Postgres by at
  most a couple of seconds.
- :func:`full_resync` — walks every ownership table in Postgres and
  rebuilds the graph from scratch. Used to seed a fresh Neo4j cluster
  and on a periodic safety-net schedule.
- :func:`apply_one_event_for_tests` — sync helper that drains exactly
  one event and applies it. Lives here (not in tests) so tests can
  call it without importing private symbols.
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from aqp.config import settings

logger = logging.getLogger(__name__)


@shared_task(
    name="aqp.tasks.ownership_tasks.drain_events",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def drain_events(self, *, max_events: int | None = None) -> dict[str, Any]:
    """Drain a batch of events from the bus and apply to the graph store."""
    from aqp.graph import get_ownership_store
    from aqp.graph.events import iter_drained_events

    limit = int(max_events or settings.ownership_sync_batch_size or 500)
    events = list(iter_drained_events(max_events=limit))
    if not events:
        return {"drained": 0}
    try:
        store = get_ownership_store()
    except Exception as exc:  # noqa: BLE001
        # If the configured store fails to construct (e.g. Neo4j down),
        # we re-emit so the next drain attempt has another shot. The
        # Redis stream is still empty at this point because
        # iter_drained_events removed them; re-emit copies.
        from aqp.graph.events import emit_ownership_event

        for ev in events:
            emit_ownership_event(ev)
        raise RuntimeError(
            f"ownership graph store unavailable; events re-queued: {exc}"
        )
    applied = store.apply_events(events)
    logger.debug("ownership drain applied %s events", applied)
    return {"drained": applied}


@shared_task(
    name="aqp.tasks.ownership_tasks.full_resync",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def full_resync(self) -> dict[str, Any]:
    """Walk every ownership-relevant table and emit upsert events.

    Idempotent: each row produces the same node + edge events whether
    it's the first or the thousandth time we run.
    """
    from aqp.graph.events import (
        OwnershipEvent,
        OwnershipEventKind,
        emit_ownership_event,
    )
    from aqp.graph.sqlalchemy_hooks import _NODE_TRANSLATORS, _build_translators
    from aqp.persistence.db import get_session
    from aqp.persistence.models_experiments import Experiment, Test
    from aqp.persistence.models_resources import Resource, ResourceRelation
    from aqp.persistence.models_tenancy import (
        Lab,
        Membership,
        Organization,
        Project,
        Team,
        User,
        Workspace,
    )

    _build_translators()

    emitted = 0
    with get_session() as session:
        for model in (
            Organization,
            User,
            Team,
            Workspace,
            Project,
            Lab,
            Experiment,
            Test,
            Resource,
        ):
            for row in session.query(model).yield_per(500):
                kind = f"{model.__module__}.{model.__name__}"
                node_fn = _NODE_TRANSLATORS.get(kind)
                node = node_fn(row) if node_fn else None
                if node is not None:
                    emit_ownership_event(
                        OwnershipEvent(
                            kind=OwnershipEventKind.UPSERT_NODE, node=node
                        )
                    )
                    emitted += 1

        # Edges come from a separate pass so the drain task always sees
        # node upserts before the edges that reference them.
        from aqp.graph.sqlalchemy_hooks import _EDGE_TRANSLATORS

        for model in (
            Team,
            Workspace,
            Project,
            Lab,
            Membership,
            Experiment,
            Test,
            Resource,
            ResourceRelation,
        ):
            for row in session.query(model).yield_per(500):
                kind = f"{model.__module__}.{model.__name__}"
                edge_fn = _EDGE_TRANSLATORS.get(kind)
                if edge_fn is None:
                    continue
                for edge in edge_fn(row):
                    emit_ownership_event(
                        OwnershipEvent(
                            kind=OwnershipEventKind.UPSERT_EDGE, edge=edge
                        )
                    )
                    emitted += 1

    logger.info("ownership full_resync emitted %s events", emitted)
    return {"emitted": emitted}


def apply_one_event_for_tests() -> dict[str, Any]:
    """Sync drain helper used by the test suite."""
    return drain_events(max_events=1)  # type: ignore[misc]


__all__ = ["apply_one_event_for_tests", "drain_events", "full_resync"]
