"""Resource-scoped list filter (ADR 003).

Every list endpoint in the control plane (and the in-AQP
``/control-plane/*`` proxy) MUST pass its result list through
:func:`filter_resources` before returning. Users with the
``admin:cluster`` scope see everything; everyone else sees only
resources whose ``id`` is in their
``https://aqp.internal/resources`` claim.

This is the canonical "never return a resource not in the user's
claim" enforcement point — frontend filtering is defence in depth,
not defence in chief.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

from aqp_platform_core.auth.claims import CLAIM_RESOURCES, extract_claim
from aqp_platform_core.auth.rbac import SCOPE_ADMIN_CLUSTER

T = TypeVar("T")


def has_admin_cluster(payload: dict[str, Any]) -> bool:
    """Return ``True`` when the JWT payload carries the ``admin:cluster`` scope."""
    raw_scope = payload.get("scope", "")
    if isinstance(raw_scope, str):
        scopes = set(raw_scope.split())
    elif isinstance(raw_scope, (list, tuple)):
        scopes = {str(s) for s in raw_scope}
    else:
        scopes = set()

    # Also accept Auth0 RBAC ``permissions`` array.
    permissions = payload.get("permissions") or []
    if isinstance(permissions, list):
        scopes.update(str(p) for p in permissions)

    return SCOPE_ADMIN_CLUSTER in scopes


def user_resource_ids(payload: dict[str, Any]) -> set[str]:
    """Return the set of resource IDs the user is explicitly granted.

    Reads the canonical (``https://aqp.internal/resources``) and legacy
    (``https://aqp/resources``) claim namespaces. Returns an empty set
    when the claim is absent — combined with the ``admin:cluster``
    bypass check in :func:`filter_resources`, that means "no
    resources" for non-admin users (deny by default).
    """
    raw = extract_claim(payload, CLAIM_RESOURCES, default=None)
    if not raw:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(item) for item in raw if item is not None}
    if isinstance(raw, str):
        # Support comma-separated claim shape from older Actions.
        return {part.strip() for part in raw.split(",") if part.strip()}
    return set()


def filter_resources(
    items: Iterable[T],
    payload: dict[str, Any],
    *,
    id_getter: Callable[[T], str | None] = None,
) -> list[T]:
    """Return only the items the JWT subject is allowed to see.

    Bypassed entirely for ``admin:cluster``. For everyone else, returns
    items whose ID (default: ``item["id"]`` for dicts, ``item.id`` for
    objects) is present in
    ``payload["https://aqp.internal/resources"]``.

    Provide ``id_getter`` to customise the ID extraction for non-dict /
    non-attribute item types.
    """
    items_list = list(items)
    if has_admin_cluster(payload):
        return items_list

    allowed = user_resource_ids(payload)
    if not allowed:
        # No claim and no admin bypass -> deny everything.
        return []

    getter = id_getter or _default_id_getter
    return [item for item in items_list if (getter(item) in allowed)]


def _default_id_getter(item: Any) -> str | None:
    """Default ID extractor: ``item["id"]`` for mappings, ``item.id`` for objects."""
    if isinstance(item, dict):
        value = item.get("id")
        return None if value is None else str(value)
    value = getattr(item, "id", None)
    return None if value is None else str(value)


__all__ = [
    "filter_resources",
    "has_admin_cluster",
    "user_resource_ids",
]
