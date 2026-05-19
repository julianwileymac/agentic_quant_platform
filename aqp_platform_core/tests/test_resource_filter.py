"""resource_filter — admin bypass + claim intersect (ADR 003)."""
from __future__ import annotations

from aqp_platform_core.auth import (
    SCOPE_ADMIN_CLUSTER,
    SCOPE_READ_INFRA,
    filter_resources,
    has_admin_cluster,
    user_resource_ids,
)


def _payload(*, scope: str = "", resources: list[str] | None = None) -> dict:
    p: dict = {"scope": scope}
    if resources is not None:
        p["https://aqp.internal/resources"] = resources
    return p


def test_admin_cluster_sees_everything() -> None:
    payload = _payload(scope=SCOPE_ADMIN_CLUSTER, resources=[])
    items = [{"id": "a"}, {"id": "b"}]
    assert filter_resources(items, payload) == items


def test_non_admin_with_no_claim_sees_nothing() -> None:
    payload = _payload(scope=SCOPE_READ_INFRA)
    items = [{"id": "a"}, {"id": "b"}]
    assert filter_resources(items, payload) == []


def test_non_admin_intersects_resources_claim() -> None:
    payload = _payload(scope=SCOPE_READ_INFRA, resources=["a", "c"])
    items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert [i["id"] for i in filter_resources(items, payload)] == ["a", "c"]


def test_legacy_claims_namespace_still_readable() -> None:
    payload: dict = {
        "scope": SCOPE_READ_INFRA,
        "https://aqp/resources": ["legacy-1"],
    }
    items = [{"id": "legacy-1"}, {"id": "other"}]
    assert [i["id"] for i in filter_resources(items, payload)] == ["legacy-1"]


def test_canonical_namespace_wins_when_both_present() -> None:
    payload: dict = {
        "scope": SCOPE_READ_INFRA,
        "https://aqp.internal/resources": ["new"],
        "https://aqp/resources": ["old"],
    }
    items = [{"id": "new"}, {"id": "old"}]
    assert [i["id"] for i in filter_resources(items, payload)] == ["new"]


def test_user_resource_ids_handles_comma_separated_string() -> None:
    payload: dict = {"https://aqp.internal/resources": "a,b ,c , "}
    assert user_resource_ids(payload) == {"a", "b", "c"}


def test_permissions_array_grants_admin_cluster() -> None:
    payload: dict = {"permissions": ["admin:cluster", "read:infrastructure"]}
    assert has_admin_cluster(payload)


def test_object_id_getter_via_attribute() -> None:
    class Item:
        def __init__(self, id: str) -> None:
            self.id = id

    payload = _payload(scope=SCOPE_READ_INFRA, resources=["x"])
    items = [Item("x"), Item("y")]
    out = filter_resources(items, payload)
    assert [i.id for i in out] == ["x"]


def test_custom_id_getter_overrides_default() -> None:
    payload = _payload(scope=SCOPE_READ_INFRA, resources=["alpha"])
    items = [
        {"slug": "alpha", "id": "ignored"},
        {"slug": "beta", "id": "ignored"},
    ]
    out = filter_resources(items, payload, id_getter=lambda i: i["slug"])
    assert [i["slug"] for i in out] == ["alpha"]
