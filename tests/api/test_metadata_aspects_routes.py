from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata import write_aspect
from aqp.metadata.openmetadata import DatasetTable, LineageEdge, MlModel, TableColumn
from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

URN_DATASET = "urn:aqp:dataset:prod:aqp_silver_alpha_vantage.daily_bars"
URN_FEATURES = "urn:aqp:dataset:prod:aqp_gold_alpha.features_v1"
URN_MODEL = "urn:aqp:mlmodel:prod:aqp_models.ridge_alpha_v1"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import metadata_aspects

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[MetadataEntity.__table__, EntityAspect.__table__],
    )
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(metadata_aspects, "get_session", _patched_get_session)

    with Session() as session:
        _seed(session)
        session.commit()

    app = FastAPI()
    app.include_router(metadata_aspects.router, prefix="/metadata/aspects", tags=["metadata"])
    return TestClient(app)


def _seed(session) -> None:  # type: ignore[no-untyped-def]
    write_aspect(
        session,
        URN_DATASET,
        "datasetProperties",
        DatasetTable(
            urn=URN_DATASET,
            name="daily_bars",
            iceberg_identifier="aqp_silver_alpha_vantage.daily_bars",
            medallion_layer="silver",
            columns=[
                TableColumn(name="ts", data_type="timestamp", nullable=False),
                TableColumn(name="close", data_type="float64", nullable=False),
            ],
            description="Daily OHLCV bars",
        ),
        created_by="seed",
    )
    write_aspect(
        session,
        URN_DATASET,
        "datasetProperties",
        DatasetTable(
            urn=URN_DATASET,
            name="daily_bars",
            iceberg_identifier="aqp_silver_alpha_vantage.daily_bars",
            medallion_layer="silver",
            columns=[
                TableColumn(name="ts", data_type="timestamp", nullable=False),
                TableColumn(name="close", data_type="float64", nullable=False),
                TableColumn(name="volume", data_type="int64", nullable=False),
            ],
            description="Daily OHLCV bars with volume",
        ),
        created_by="seed",
    )
    write_aspect(
        session,
        URN_FEATURES,
        "datasetProperties",
        DatasetTable(
            urn=URN_FEATURES,
            name="features_v1",
            iceberg_identifier="aqp_gold_alpha.features_v1",
            medallion_layer="gold",
            columns=[
                TableColumn(name="vt_symbol", data_type="string", nullable=False),
                TableColumn(name="alpha_5d", data_type="float64", nullable=False),
            ],
            description="Gold alpha features",
        ),
        created_by="seed",
    )
    write_aspect(
        session,
        URN_MODEL,
        "mlModelMetadata",
        MlModel(
            urn=URN_MODEL,
            name="ridge_alpha_v1",
            algorithm="ridge",
            target="forward_return_1d",
            status="Production",
        ),
        created_by="seed",
    )
    write_aspect(
        session,
        URN_DATASET,
        "lineageEdge",
        LineageEdge(
            from_entity=URN_DATASET,
            to_entity=URN_FEATURES,
            edge_type="table_to_feature",
            metadata={"run_id": "seed-1"},
        ),
        created_by="seed",
    )
    write_aspect(
        session,
        URN_FEATURES,
        "lineageEdge",
        LineageEdge(
            from_entity=URN_FEATURES,
            to_entity=URN_MODEL,
            edge_type="feature_to_model",
            metadata={"run_id": "seed-2"},
        ),
        created_by="seed",
    )


def test_list_entities_returns_seeded_rows(client: TestClient) -> None:
    response = client.get("/metadata/aspects/entities", params={"limit": 50})
    assert response.status_code == 200, response.text
    payload = response.json()
    urns = {item["urn"] for item in payload["items"]}
    assert URN_DATASET in urns
    assert URN_FEATURES in urns
    assert URN_MODEL in urns
    assert payload["total"] >= 3


def test_entity_detail_returns_latest_aspects(client: TestClient) -> None:
    encoded_urn = quote(URN_DATASET, safe="")
    response = client.get(f"/metadata/aspects/entities/{encoded_urn}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["urn"] == URN_DATASET
    assert payload["entity_type"] == "dataset"
    assert payload["aspects"]["datasetProperties"]["version"] == 2
    assert payload["aspects"]["lineageEdge"]["version"] == 1


def test_entity_history_supports_aspect_filter_desc_order(client: TestClient) -> None:
    encoded_urn = quote(URN_DATASET, safe="")
    response = client.get(
        f"/metadata/aspects/entities/{encoded_urn}/history",
        params={"aspect_name": "datasetProperties", "limit": 10},
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    versions = [row["version"] for row in rows]
    assert versions == [2, 1]
    assert rows[0]["aspect_name"] == "datasetProperties"
    assert "payload_hash" in rows[0]


def test_lineage_endpoint_returns_structured_payload(client: TestClient) -> None:
    encoded_urn = quote(URN_DATASET, safe="")
    response = client.get(
        f"/metadata/aspects/lineage/{encoded_urn}",
        params={"depth": 2, "direction": "both"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entity"] == URN_DATASET
    downstream_targets = {row["to_entity"] for row in payload["downstream_edges"]}
    assert URN_FEATURES in downstream_targets
    assert URN_MODEL in downstream_targets


def test_stats_endpoint_returns_counts(client: TestClient) -> None:
    response = client.get("/metadata/aspects/stats")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entity_count_by_type"]["dataset"] >= 2
    assert payload["entity_count_by_type"]["mlmodel"] >= 1
    assert payload["aspect_count_by_name"]["datasetProperties"] >= 3
    assert payload["aspect_count_by_name"]["lineageEdge"] >= 2
    assert len(payload["recent_writes"]) >= 1
