"""Tests for the knowledge-graph entity API."""
from __future__ import annotations

import pytest

from aqp.persistence.models_entities import EntityRelationship, Issuer


@pytest.fixture
def seed_issuers(in_memory_db) -> tuple[str, str, str]:
    """Create a small KG fixture: parent → subsidiary, plus one peer."""
    from aqp.api.routes import entities as entities_mod

    with entities_mod.get_session() as session:
        parent = Issuer(
            name="Test Holding Co",
            kind="corporate",
            country="USA",
            entity_status="active",
        )
        sub = Issuer(
            name="Test Subsidiary Inc",
            kind="corporate",
            country="USA",
            entity_status="active",
        )
        peer = Issuer(
            name="Test Peer Corp",
            kind="corporate",
            country="USA",
            entity_status="active",
        )
        session.add_all([parent, sub, peer])
        session.flush()
        rel = EntityRelationship(
            from_kind="issuer",
            from_entity_id=parent.id,
            to_kind="issuer",
            to_entity_id=sub.id,
            relationship_type="parent_subsidiary",
            ownership_pct=0.8,
        )
        session.add(rel)
        session.flush()
        return parent.id, sub.id, peer.id


def test_list_issuers_filter_by_q(seed_issuers: tuple[str, str, str]) -> None:
    from aqp.api.routes.entities import list_issuers

    rows = list_issuers(q="Holding", limit=10, offset=0)
    assert any(r.name == "Test Holding Co" for r in rows)


def test_get_issuer_returns_relationships_and_classifications(
    seed_issuers: tuple[str, str, str],
) -> None:
    from aqp.api.routes.entities import get_issuer

    parent_id, sub_id, _ = seed_issuers
    detail = get_issuer(parent_id)
    assert detail.id == parent_id
    rel_to = {r["to_entity_id"] for r in detail.relationships}
    assert sub_id in rel_to


def test_graph_traversal_includes_subsidiary(
    seed_issuers: tuple[str, str, str],
) -> None:
    from aqp.api.routes.entities import issuer_graph

    parent_id, sub_id, _ = seed_issuers
    g = issuer_graph(root_id=parent_id, depth=1, max_nodes=50)
    # ensure tagged
    assert g
    node_ids = {n.id for n in g.nodes}
    assert parent_id in node_ids
    assert sub_id in node_ids
    edge_pairs = {(e.from_id, e.to_id) for e in g.edges}
    assert (parent_id, sub_id) in edge_pairs


def test_get_relationships(seed_issuers: tuple[str, str, str]) -> None:
    from aqp.api.routes.entities import get_relationships

    parent_id, sub_id, _ = seed_issuers
    rels = get_relationships(parent_id)
    assert any(r["to_entity_id"] == sub_id for r in rels)


def test_unknown_issuer_404(seed_issuers: tuple[str, str, str]) -> None:
    from fastapi import HTTPException

    from aqp.api.routes.entities import get_issuer

    with pytest.raises(HTTPException) as exc:
        get_issuer("does-not-exist-uuid")
    assert exc.value.status_code == 404
