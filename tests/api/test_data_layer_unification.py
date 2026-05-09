"""API tests for the data-layer unification routes.

Covers ``/data-control/lineage``, ``/data-control/mcp/tools``,
``/data-control/catalog/browse``, and ``/data/entities/...``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def app(in_memory_db):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI

    from aqp.api.routes import data_control, data_entities

    app = FastAPI()
    app.include_router(data_control.router)
    app.include_router(data_entities.router)
    return app


@pytest.fixture
def client(app):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_lineage_endpoint_returns_empty_list(client) -> None:
    response = client.get("/data-control/lineage")
    assert response.status_code == 200
    assert response.json() == []


def test_lineage_endpoint_filters_by_kind(client, in_memory_db) -> None:
    Session = in_memory_db
    from aqp.persistence.models_lineage import DataLineageEvent

    with Session() as session:
        session.add_all(
            [
                DataLineageEvent(
                    transform_kind="materialize",
                    target_table_id="aqp_silver_alpha.daily_bars",
                    actor="executor.local",
                ),
                DataLineageEvent(
                    transform_kind="iceberg_append",
                    target_table_id="aqp_silver_alpha.daily_bars",
                    actor="iceberg_catalog",
                ),
            ]
        )
        session.commit()
    response = client.get("/data-control/lineage", params={"transform_kind": "materialize"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["transform_kind"] == "materialize"


def test_mcp_tools_index_returns_descriptors(client) -> None:
    response = client.get("/data-control/mcp/tools")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] > 0
    names = {tool["name"] for tool in payload["tools"]}
    assert "data.catalog.browse" in names


def test_catalog_browse_returns_filtered_rows(client, in_memory_db) -> None:
    Session = in_memory_db
    from aqp.persistence.models import DatasetCatalog

    with Session() as session:
        session.add_all(
            [
                DatasetCatalog(
                    name="alpha_daily",
                    provider="alpha_vantage",
                    domain="market.bars",
                    iceberg_identifier="aqp_silver_alpha_vantage.daily_bars",
                    medallion_layer="silver",
                    business_metadata={"data_owner": "data-team"},
                ),
                DatasetCatalog(
                    name="raw_drop",
                    provider="alpha_vantage",
                    domain="market.bars",
                    iceberg_identifier="aqp_bronze_alpha_vantage.daily_bars",
                    medallion_layer="bronze",
                ),
            ]
        )
        session.commit()
    response = client.get("/data-control/catalog/browse", params={"layer": "silver"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["rows"][0]["medallion_layer"] == "silver"


def test_data_entity_routes_404_for_unknown_symbol(client) -> None:
    response = client.get("/data/entities/UNKNOWN.NASDAQ")
    assert response.status_code == 404


def test_data_entity_routes_load_known_symbol(client, in_memory_db) -> None:
    Session = in_memory_db
    from aqp.persistence.models import Instrument

    with Session() as session:
        session.add(
            Instrument(
                vt_symbol="AAPL.NASDAQ",
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="equity",
                security_type="spot",
                instrument_class="spot",
            )
        )
        session.commit()
    response = client.get("/data/entities/AAPL.NASDAQ")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product_kind"] == "equity"
    assert payload["entity_id"] == "AAPL.NASDAQ"


def test_mcp_invoke_endpoint_is_callable(client, in_memory_db) -> None:
    Session = in_memory_db
    from aqp.persistence.models import DatasetCatalog

    with Session() as session:
        session.add(
            DatasetCatalog(
                name="alpha_daily",
                provider="alpha_vantage",
                domain="market.bars",
                iceberg_identifier="aqp_silver_alpha_vantage.daily_bars",
                medallion_layer="silver",
                business_metadata={"data_owner": "data-team"},
            )
        )
        session.commit()

    response = client.post(
        "/data-control/mcp/tools/data.catalog.browse/invoke",
        json={
            "arguments": {"layer": "silver"},
            "granted_scopes": ["data:read"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    rows = payload["result"]["data"]
    assert any(row["medallion_layer"] == "silver" for row in rows)
