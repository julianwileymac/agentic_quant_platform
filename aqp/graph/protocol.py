"""Graph protocol + node / edge dataclasses + singleton factory.

This module is intentionally backend-agnostic — it neither imports
Neo4j nor SQLAlchemy directly. Concrete stores live in
:mod:`aqp.graph.postgres_store` and :mod:`aqp.graph.neo4j_store` and
are loaded lazily inside :func:`get_ownership_store` so a deploy that
sets ``AQP_OWNERSHIP_GRAPH_STORE=postgres`` doesn't pay the cost of
the Neo4j driver import.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings


# ---------------------------------------------------------------------------
# Node + edge vocabulary
# ---------------------------------------------------------------------------

# Canonical node kinds — every label on a Neo4j ``(:Kind {id})`` node and
# the value of the ``kind`` column on the recursive Postgres view. New
# kinds get added here once the corresponding Postgres + Neo4j projectors
# learn how to upsert them; new code reading the graph should pattern-
# match against this list rather than re-deriving it.
OWNERSHIP_NODE_KINDS: tuple[str, ...] = (
    "Organization",
    "Team",
    "User",
    "Workspace",
    "Project",
    "Lab",
    "Experiment",
    "Test",
    "Resource",
    "Strategy",
    "Dataset",
    "Bot",
    "Agent",
    "RLExperiment",
    "AnalysisSpec",
    "Sink",
    "AirbyteConnector",
    "Run",
)


# Canonical edge kinds. Lower-cased + snake-cased so Cypher relationship
# types render uniformly. Direction is "from -> to" in the edge data.
OWNERSHIP_EDGE_KINDS: tuple[str, ...] = (
    "BELONGS_TO_ORG",       # Team -> Organization
    "HAS_TEAM",             # Organization -> Team
    "HAS_WORKSPACE",        # Organization -> Workspace
    "HAS_PROJECT",          # Workspace -> Project
    "HAS_LAB",              # Workspace -> Lab
    "MEMBER_OF",            # User -> (Org|Team|Workspace|Project|Lab)
    "OWNS",                 # (Org|Team|User|Workspace|Project) -> Resource
    "USES",                 # Bot/Strategy -> Resource/Dataset
    "DERIVED_FROM",         # Resource -> Resource
    "RAN",                  # Test -> Run
    "OF_KIND",              # Run -> Strategy
    "PARENT_OF",            # Experiment -> Experiment (nesting)
    "IN_EXPERIMENT",        # Run/Test -> Experiment
    "IN_TEST",              # Run -> Test
    "READ_FROM",            # Run -> Dataset
    "WROTE_TO",             # Run -> Dataset
    "IN_WORKSPACE",         # Project/Lab/Resource/Experiment -> Workspace
    "IN_PROJECT",           # Resource/Experiment/Run -> Project
    "IN_LAB",               # Resource/Experiment -> Lab
)


@dataclass(frozen=True)
class OwnershipNode:
    """A node in the ownership graph.

    ``id`` is the Postgres UUID (or composite key for derived nodes
    like ``Run`` which carry their typed table as a prefix —
    ``backtest_runs:<uuid>`` etc.). ``kind`` matches
    :data:`OWNERSHIP_NODE_KINDS`. ``properties`` is a free-form
    dictionary the Neo4j projector flattens onto the node.
    """

    id: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OwnershipEdge:
    """An edge in the ownership graph."""

    from_id: str
    from_kind: str
    to_id: str
    to_kind: str
    relation: str
    properties: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class OwnershipGraphStore(ABC):
    """Backend-agnostic ownership graph contract.

    Read-only callers care about :meth:`traverse`,
    :meth:`list_resources_visible_to`, and :meth:`who_can_read`.
    Write callers (the Celery drain task, the bootstrap script) use
    :meth:`upsert_node`, :meth:`upsert_edge`, :meth:`delete_node`,
    :meth:`delete_edge`, and the bulk :meth:`apply_events`.

    Implementations MUST be idempotent — replaying a stream of
    :class:`OwnershipEvent` objects must converge on the same graph
    regardless of order or repetition.
    """

    name: str = "abstract"

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Quick liveness check; returns ``{"ok": bool, "kind": str, ...}``."""

    @abstractmethod
    def upsert_node(self, node: OwnershipNode) -> None:
        """Create-or-merge a node by ``(kind, id)``."""

    @abstractmethod
    def upsert_edge(self, edge: OwnershipEdge) -> None:
        """Create-or-merge an edge by ``(from_kind, from_id, relation, to_kind, to_id)``."""

    @abstractmethod
    def delete_node(self, kind: str, identifier: str) -> None:
        """Detach and delete a node + every edge that touches it."""

    @abstractmethod
    def delete_edge(self, edge: OwnershipEdge) -> None:
        """Delete one edge by its full coordinates."""

    @abstractmethod
    def traverse(
        self,
        *,
        start_kind: str,
        start_id: str,
        edge_kinds: list[str] | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Walk outwards from a node, returning ``{nodes: [...], edges: [...]}``."""

    @abstractmethod
    def list_resources_visible_to(
        self,
        *,
        user_id: str,
        resource_type: str | None = None,
        limit: int = 200,
    ) -> list[OwnershipNode]:
        """Resources reachable from a user via the membership graph."""

    @abstractmethod
    def who_can_read(
        self,
        *,
        resource_id: str,
    ) -> list[dict[str, Any]]:
        """List ``(user_id, role, scope_kind, scope_id)`` tuples with read access."""

    def apply_events(self, events: list[Any]) -> int:
        """Apply a batch of :class:`OwnershipEvent` rows.

        Default implementation dispatches per-event via the abstract
        methods. Concrete stores may override to batch writes (e.g.
        a single Cypher UNWIND for Neo4j).
        """
        from aqp.graph.events import OwnershipEventKind

        applied = 0
        for ev in events:
            kind = getattr(ev, "kind", None)
            if kind == OwnershipEventKind.UPSERT_NODE and ev.node is not None:
                self.upsert_node(ev.node)
            elif kind == OwnershipEventKind.UPSERT_EDGE and ev.edge is not None:
                self.upsert_edge(ev.edge)
            elif kind == OwnershipEventKind.DELETE_NODE and ev.node is not None:
                self.delete_node(ev.node.kind, ev.node.id)
            elif kind == OwnershipEventKind.DELETE_EDGE and ev.edge is not None:
                self.delete_edge(ev.edge)
            applied += 1
        return applied


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_STORE: OwnershipGraphStore | None = None


def get_ownership_store() -> OwnershipGraphStore:
    """Return the configured store, building it lazily.

    ``AQP_OWNERSHIP_GRAPH_STORE`` picks between ``postgres`` (default
    when Neo4j is offline) and ``neo4j``. Other values raise — there
    are only two implementations today.
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    backend = str(getattr(settings, "ownership_graph_store", "postgres") or "postgres").lower()
    if backend == "neo4j":
        from aqp.graph.neo4j_store import Neo4jOwnershipGraphStore

        _STORE = Neo4jOwnershipGraphStore()
    elif backend == "postgres":
        from aqp.graph.postgres_store import PostgresOwnershipGraphStore

        _STORE = PostgresOwnershipGraphStore()
    else:
        raise ValueError(
            f"Unknown AQP_OWNERSHIP_GRAPH_STORE={backend!r}; "
            "expected 'postgres' or 'neo4j'"
        )
    return _STORE


def reset_ownership_store_for_tests() -> None:
    """Test helper — wipes the cached singleton."""
    global _STORE
    _STORE = None


__all__ = [
    "OWNERSHIP_EDGE_KINDS",
    "OWNERSHIP_NODE_KINDS",
    "OwnershipEdge",
    "OwnershipGraphStore",
    "OwnershipNode",
    "get_ownership_store",
    "reset_ownership_store_for_tests",
]
