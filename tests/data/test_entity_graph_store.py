from __future__ import annotations


def test_neo4j_upsert_entity_uses_plain_entity_label(monkeypatch) -> None:
    from aqp.data.entities.neo4j_store import Neo4jEntityGraphStore

    store = Neo4jEntityGraphStore()
    calls: list[tuple[str, dict]] = []

    def fake_write(query: str, **params):  # noqa: ANN001
        calls.append((query, params))
        return [{"entity": {"id": params["id"], **params["props"]}}]

    monkeypatch.setattr(store, "_execute_write", fake_write)

    payload = store.upsert_entity(
        {
            "id": "entity-1",
            "kind": "security",
            "canonical_name": "AAPL",
            "attributes": {"vt_symbol": "AAPL.NASDAQ"},
        }
    )

    assert payload is not None
    assert payload["id"] == "entity-1"
    assert calls
    assert "apoc" not in calls[0][0].lower()
    assert calls[0][1]["props"]["attributes_json"] == '{"vt_symbol": "AAPL.NASDAQ"}'


def test_graph_store_disabled_returns_none(monkeypatch) -> None:
    from aqp.data.entities import graph_store

    graph_store.reset_graph_store_for_tests()
    monkeypatch.setattr(graph_store.settings, "graph_store", "postgres")

    assert graph_store.get_graph_store() is None
