"""Ownership / relationship graph for AQP (Phase 2 of the multi-tenant expansion).

Postgres remains the **canonical** store for tenancy nodes and edges
(every row in ``organizations``, ``teams``, ``users``, ``memberships``,
``workspaces``, ``projects``, ``labs``, ``experiments``, ``tests``,
``resources``, ``resource_relations``, ``data_lineage_events``).
``aqp.graph`` is the projection layer that gives the MCP catalog +
ownership queries a fast multi-hop traversal surface — either by
walking those same Postgres tables (the bootstrap / fallback path) or
by mirroring the edges into Neo4j (the production path).

Public surface:

- :class:`OwnershipNode` / :class:`OwnershipEdge` — dataclass shapes.
- :class:`OwnershipGraphStore` — ABC implemented by ``postgres_store``
  and ``neo4j_store``.
- :func:`get_ownership_store` — process-wide singleton, gated by
  :attr:`Settings.ownership_graph_store`.
- :func:`emit_ownership_event` — publish an :class:`OwnershipEvent`
  (queued into Redis ``aqp:ownership:events`` and drained by
  :mod:`aqp.tasks.ownership_tasks`).
- :func:`install_sqlalchemy_hooks` — register the
  ``after_flush_postexec`` listeners that translate inserts / updates
  / deletes on the tenancy tables into events.

AGENTS.md hard rule 33 (added in this rollout): All ownership /
membership queries that traverse more than one hop MUST go through
:class:`OwnershipGraphStore`. Don't hand-write joins over
``organizations / teams / users / memberships / resources``.
"""
from __future__ import annotations

from aqp.graph.events import (
    OwnershipEvent,
    OwnershipEventKind,
    emit_ownership_event,
    iter_drained_events,
)
from aqp.graph.protocol import (
    OWNERSHIP_EDGE_KINDS,
    OWNERSHIP_NODE_KINDS,
    OwnershipEdge,
    OwnershipGraphStore,
    OwnershipNode,
    get_ownership_store,
    reset_ownership_store_for_tests,
)

__all__ = [
    "OWNERSHIP_EDGE_KINDS",
    "OWNERSHIP_NODE_KINDS",
    "OwnershipEdge",
    "OwnershipEvent",
    "OwnershipEventKind",
    "OwnershipGraphStore",
    "OwnershipNode",
    "emit_ownership_event",
    "get_ownership_store",
    "iter_drained_events",
    "reset_ownership_store_for_tests",
]


def install_sqlalchemy_hooks() -> None:
    """Register the ``after_flush_postexec`` listeners.

    Idempotent — calling more than once is a no-op. Called lazily from
    :mod:`aqp.api.main` on FastAPI startup and from
    :func:`aqp.tasks.celery_app.celery_app` worker init. Safe to skip
    in pure-script contexts that don't mutate tenancy rows.
    """
    from aqp.graph.sqlalchemy_hooks import register_hooks

    register_hooks()
