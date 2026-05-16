"""SQLAlchemy ``after_flush_postexec`` hooks that bridge Postgres commits
to :mod:`aqp.graph.events`.

The flow:

1. ORM caller commits a tenancy / experiment / resource row.
2. SQLAlchemy fires the ``after_flush_postexec`` event with the
   ``Session``'s ``new`` / ``dirty`` / ``deleted`` collections.
3. The listener inspects each row, derives the implied
   :class:`OwnershipNode` and any new / removed :class:`OwnershipEdge`,
   and pushes :class:`OwnershipEvent` rows onto the event bus.
4. :func:`aqp.tasks.ownership_tasks.drain_events` picks them up.

Idempotent + safe: every event carries the full
:class:`OwnershipNode` / :class:`OwnershipEdge`, not just an id, so
replays converge on the same Neo4j state regardless of order.

Hooks are intentionally narrow — only the tables that participate in
the ownership graph trigger emits. New tables register themselves by
adding to :data:`_NODE_TRANSLATORS` / :data:`_EDGE_TRANSLATORS`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from aqp.graph.events import (
    OwnershipEvent,
    OwnershipEventKind,
    emit_ownership_event,
)
from aqp.graph.protocol import OwnershipEdge, OwnershipNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-model translators
# ---------------------------------------------------------------------------

# A translator takes a single ORM row and returns
# ``(node, list[edge])``. The node MAY be ``None`` for rows that only
# contribute edges (e.g. ``Membership``).

NodeFn = Callable[[Any], OwnershipNode | None]
EdgeFn = Callable[[Any], list[OwnershipEdge]]


_NODE_TRANSLATORS: dict[str, NodeFn] = {}
_EDGE_TRANSLATORS: dict[str, EdgeFn] = {}


def _register(model_attr: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator binding ``(node_fn, edge_fn)`` to a model class."""

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        kind, suffix = model_attr.rsplit(":", 1)
        if suffix == "node":
            _NODE_TRANSLATORS[kind] = fn
        elif suffix == "edges":
            _EDGE_TRANSLATORS[kind] = fn
        return fn

    return _decorate


def _model_kind(row: Any) -> str:
    cls = type(row)
    return f"{cls.__module__}.{cls.__name__}"


def _build_translators() -> None:
    """Populate the per-model translators (lazy to avoid early imports)."""
    if _NODE_TRANSLATORS:
        return

    # Defer imports so this module doesn't pull every ORM into scope at
    # parse time — the orm package's __init__ already does that, but
    # this module may be imported from tests that don't want it.
    from aqp.persistence.models_tenancy import (  # noqa: WPS433 — late import
        Lab,
        Membership,
        Organization,
        Project,
        Team,
        User,
        Workspace,
    )
    from aqp.persistence.models_experiments import (  # noqa: WPS433
        Experiment,
        Test,
    )
    from aqp.persistence.models_resources import (  # noqa: WPS433
        Resource,
        ResourceRelation,
    )

    def _org_node(r: Organization) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Organization",
            properties={"slug": r.slug, "name": r.name},
        )

    def _team_node(r: Team) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Team",
            properties={"slug": r.slug, "name": r.name, "org_id": str(r.org_id)},
        )

    def _team_edges(r: Team) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.org_id),
                from_kind="Organization",
                to_id=str(r.id),
                to_kind="Team",
                relation="HAS_TEAM",
            ),
            OwnershipEdge(
                from_id=str(r.id),
                from_kind="Team",
                to_id=str(r.org_id),
                to_kind="Organization",
                relation="BELONGS_TO_ORG",
            ),
        ]

    def _user_node(r: User) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="User",
            properties={
                "email": r.email,
                "display_name": r.display_name,
                "auth_subject": r.auth_subject,
            },
        )

    def _ws_node(r: Workspace) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Workspace",
            properties={
                "slug": r.slug,
                "name": r.name,
                "org_id": str(r.org_id),
                "visibility": r.visibility,
            },
        )

    def _ws_edges(r: Workspace) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.org_id),
                from_kind="Organization",
                to_id=str(r.id),
                to_kind="Workspace",
                relation="HAS_WORKSPACE",
            ),
        ]

    def _proj_node(r: Project) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Project",
            properties={
                "slug": r.slug,
                "name": r.name,
                "workspace_id": str(r.workspace_id),
            },
        )

    def _proj_edges(r: Project) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.workspace_id),
                from_kind="Workspace",
                to_id=str(r.id),
                to_kind="Project",
                relation="HAS_PROJECT",
            )
        ]

    def _lab_node(r: Lab) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Lab",
            properties={
                "slug": r.slug,
                "name": r.name,
                "workspace_id": str(r.workspace_id),
            },
        )

    def _lab_edges(r: Lab) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.workspace_id),
                from_kind="Workspace",
                to_id=str(r.id),
                to_kind="Lab",
                relation="HAS_LAB",
            )
        ]

    def _mem_edges(r: Membership) -> list[OwnershipEdge]:
        scope_kind_map = {
            "org": "Organization",
            "team": "Team",
            "workspace": "Workspace",
            "project": "Project",
            "lab": "Lab",
        }
        to_kind = scope_kind_map.get(r.scope_kind, "Organization")
        return [
            OwnershipEdge(
                from_id=str(r.user_id),
                from_kind="User",
                to_id=str(r.scope_id),
                to_kind=to_kind,
                relation="MEMBER_OF",
                properties={
                    "role": str(r.role),
                    "live_control": bool(r.live_control),
                },
            )
        ]

    def _exp_node(r: Experiment) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Experiment",
            properties={
                "slug": r.slug,
                "name": r.name,
                "kind": r.kind,
                "status": r.status,
            },
        )

    def _exp_edges(r: Experiment) -> list[OwnershipEdge]:
        out: list[OwnershipEdge] = []
        if r.project_id:
            out.append(
                OwnershipEdge(
                    from_id=str(r.id),
                    from_kind="Experiment",
                    to_id=str(r.project_id),
                    to_kind="Project",
                    relation="IN_PROJECT",
                )
            )
        if r.lab_id:
            out.append(
                OwnershipEdge(
                    from_id=str(r.id),
                    from_kind="Experiment",
                    to_id=str(r.lab_id),
                    to_kind="Lab",
                    relation="IN_LAB",
                )
            )
        if r.parent_experiment_id:
            out.append(
                OwnershipEdge(
                    from_id=str(r.parent_experiment_id),
                    from_kind="Experiment",
                    to_id=str(r.id),
                    to_kind="Experiment",
                    relation="PARENT_OF",
                )
            )
        return out

    def _test_node(r: Test) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Test",
            properties={
                "slug": r.slug,
                "name": r.name,
                "assertion_kind": r.assertion_kind,
                "passed": r.passed,
            },
        )

    def _test_edges(r: Test) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.id),
                from_kind="Test",
                to_id=str(r.experiment_id),
                to_kind="Experiment",
                relation="IN_EXPERIMENT",
            )
        ]

    def _res_node(r: Resource) -> OwnershipNode:
        return OwnershipNode(
            id=str(r.id),
            kind="Resource",
            properties={
                "slug": r.slug,
                "name": r.name,
                "resource_type": r.resource_type,
                "uri": r.uri,
                "owner_scope_kind": r.owner_scope_kind,
                "owner_scope_id": str(r.owner_scope_id),
                "visibility": r.visibility,
            },
        )

    def _res_edges(r: Resource) -> list[OwnershipEdge]:
        scope_map = {
            "organization": "Organization",
            "team": "Team",
            "workspace": "Workspace",
            "project": "Project",
            "user": "User",
        }
        owner_kind = scope_map.get(r.owner_scope_kind, "Organization")
        out: list[OwnershipEdge] = [
            OwnershipEdge(
                from_id=str(r.owner_scope_id),
                from_kind=owner_kind,
                to_id=str(r.id),
                to_kind="Resource",
                relation="OWNS",
            ),
        ]
        if r.project_id:
            out.append(
                OwnershipEdge(
                    from_id=str(r.id),
                    from_kind="Resource",
                    to_id=str(r.project_id),
                    to_kind="Project",
                    relation="IN_PROJECT",
                )
            )
        if r.workspace_id:
            out.append(
                OwnershipEdge(
                    from_id=str(r.id),
                    from_kind="Resource",
                    to_id=str(r.workspace_id),
                    to_kind="Workspace",
                    relation="IN_WORKSPACE",
                )
            )
        return out

    def _rel_edges(r: ResourceRelation) -> list[OwnershipEdge]:
        return [
            OwnershipEdge(
                from_id=str(r.from_id),
                from_kind="Resource",
                to_id=str(r.to_id),
                to_kind="Resource",
                relation=str(r.relation).upper(),
            )
        ]

    _NODE_TRANSLATORS[f"{Organization.__module__}.{Organization.__name__}"] = _org_node
    _NODE_TRANSLATORS[f"{Team.__module__}.{Team.__name__}"] = _team_node
    _NODE_TRANSLATORS[f"{User.__module__}.{User.__name__}"] = _user_node
    _NODE_TRANSLATORS[f"{Workspace.__module__}.{Workspace.__name__}"] = _ws_node
    _NODE_TRANSLATORS[f"{Project.__module__}.{Project.__name__}"] = _proj_node
    _NODE_TRANSLATORS[f"{Lab.__module__}.{Lab.__name__}"] = _lab_node
    _NODE_TRANSLATORS[f"{Experiment.__module__}.{Experiment.__name__}"] = _exp_node
    _NODE_TRANSLATORS[f"{Test.__module__}.{Test.__name__}"] = _test_node
    _NODE_TRANSLATORS[f"{Resource.__module__}.{Resource.__name__}"] = _res_node

    _EDGE_TRANSLATORS[f"{Team.__module__}.{Team.__name__}"] = _team_edges
    _EDGE_TRANSLATORS[f"{Workspace.__module__}.{Workspace.__name__}"] = _ws_edges
    _EDGE_TRANSLATORS[f"{Project.__module__}.{Project.__name__}"] = _proj_edges
    _EDGE_TRANSLATORS[f"{Lab.__module__}.{Lab.__name__}"] = _lab_edges
    _EDGE_TRANSLATORS[f"{Membership.__module__}.{Membership.__name__}"] = _mem_edges
    _EDGE_TRANSLATORS[f"{Experiment.__module__}.{Experiment.__name__}"] = _exp_edges
    _EDGE_TRANSLATORS[f"{Test.__module__}.{Test.__name__}"] = _test_edges
    _EDGE_TRANSLATORS[f"{Resource.__module__}.{Resource.__name__}"] = _res_edges
    _EDGE_TRANSLATORS[
        f"{ResourceRelation.__module__}.{ResourceRelation.__name__}"
    ] = _rel_edges


# ---------------------------------------------------------------------------
# Event-bus emit helpers
# ---------------------------------------------------------------------------


def _emit_for_row(row: Any, *, deleted: bool) -> None:
    """Translate one ORM row into ownership events and publish."""
    kind = _model_kind(row)
    node_fn = _NODE_TRANSLATORS.get(kind)
    edge_fn = _EDGE_TRANSLATORS.get(kind)
    try:
        node = node_fn(row) if node_fn else None
        edges = edge_fn(row) if edge_fn else []
    except Exception:  # noqa: BLE001
        logger.debug(
            "ownership translator raised for %s; dropping event", kind, exc_info=True
        )
        return

    if node is not None:
        emit_ownership_event(
            OwnershipEvent(
                kind=OwnershipEventKind.DELETE_NODE
                if deleted
                else OwnershipEventKind.UPSERT_NODE,
                node=node,
            )
        )
    for edge in edges:
        emit_ownership_event(
            OwnershipEvent(
                kind=OwnershipEventKind.DELETE_EDGE
                if deleted
                else OwnershipEventKind.UPSERT_EDGE,
                edge=edge,
            )
        )


# Per-session capture buffer. ``before_flush`` snapshots rows while
# session.new / dirty / deleted are still populated; ``after_flush_postexec``
# emits events using the snapshot (by which point the rows have their
# DB-assigned defaults applied — e.g. ``project_id`` from
# ProjectScopedMixin's default).
_CAPTURE_KEY = "_aqp_ownership_capture"


def _before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    """Snapshot the rows that are about to flush.

    Only this hook has access to ``session.new`` / ``dirty`` /
    ``deleted`` — :event:`after_flush_postexec` clears them as part of
    the flush bookkeeping.
    """
    try:
        capture = {
            "new": list(session.new),
            "dirty": list(session.dirty),
            "deleted": list(session.deleted),
        }
    except Exception:  # noqa: BLE001
        return
    session.info[_CAPTURE_KEY] = capture


def _after_flush_postexec(session: Session, _flush_context: Any) -> None:
    """Emit ownership events for every row captured in ``before_flush``.

    Runs after the flush SQL completes, so rows carry their final
    DB-assigned values (defaults, autoincrement ids, etc.). Other
    listeners running in the same cycle (lineage writer, FinOps
    stamping) are untouched.
    """
    capture = session.info.pop(_CAPTURE_KEY, None)
    if not capture:
        return
    _build_translators()
    try:
        for row in capture["new"]:
            _emit_for_row(row, deleted=False)
        for row in capture["dirty"]:
            _emit_for_row(row, deleted=False)
        for row in capture["deleted"]:
            _emit_for_row(row, deleted=True)
    except Exception:  # noqa: BLE001
        # The cache layer convention: never let the hook take down the
        # request. The periodic resync task heals any missed events.
        logger.debug("ownership after_flush_postexec failed", exc_info=True)


# ---------------------------------------------------------------------------
# Registration (idempotent)
# ---------------------------------------------------------------------------

_HOOKS_REGISTERED = False


def register_hooks() -> None:
    """Install the ``before_flush`` + ``after_flush_postexec`` listeners.

    Idempotent: re-invocation is a no-op. Called by
    :func:`aqp.graph.install_sqlalchemy_hooks`.
    """
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_flush_postexec", _after_flush_postexec)
    _HOOKS_REGISTERED = True


def unregister_hooks_for_tests() -> None:
    """Test helper — uninstall the listeners so subsequent tests start clean."""
    global _HOOKS_REGISTERED
    if not _HOOKS_REGISTERED:
        return
    event.remove(Session, "before_flush", _before_flush)
    event.remove(Session, "after_flush_postexec", _after_flush_postexec)
    _HOOKS_REGISTERED = False


__all__ = [
    "register_hooks",
    "unregister_hooks_for_tests",
]
