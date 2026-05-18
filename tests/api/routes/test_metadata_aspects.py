from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.persistence.models import Base
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

URN_DATASET = "urn:aqp:dataset:prod:aqp_silver_prices.daily_bars"
URN_MODEL = "urn:aqp:mlmodel:prod:aqp_model.ridge_v1"


def _hash_payload(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import metadata_aspects
    from aqp.data.mcp.tools import aspects as aspects_tools

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
    monkeypatch.setattr(aspects_tools, "get_session", _patched_get_session)

    with Session() as session:
        session.add_all(
            [
                MetadataEntity(
                    urn=URN_DATASET,
                    entity_type="dataset",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
                MetadataEntity(
                    urn=URN_MODEL,
                    entity_type="mlmodel",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
            ]
        )
        ds_props_v1 = {"description": "daily bars", "owner": "data"}
        ds_props_v2 = {"description": "daily bars v2", "owner": "data"}
        lineage_edge = {
            "from_entity": URN_DATASET,
            "to_entity": URN_MODEL,
            "edge_type": "table_to_feature",
            "metadata": {"run_id": "seed-run"},
        }
        model_meta = {
            "urn": URN_MODEL,
            "name": "ridge_v1",
            "algorithm": "ridge",
            "target": "forward_return_1d",
            "status": "Production",
        }
        session.add_all(
            [
                EntityAspect(
                    id="asp-1",
                    urn=URN_DATASET,
                    aspect_name="datasetProperties",
                    version=1,
                    payload=ds_props_v1,
                    payload_hash=_hash_payload(ds_props_v1),
                    system_metadata={},
                    created_by="seed",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
                EntityAspect(
                    id="asp-2",
                    urn=URN_DATASET,
                    aspect_name="datasetProperties",
                    version=2,
                    payload=ds_props_v2,
                    payload_hash=_hash_payload(ds_props_v2),
                    system_metadata={"source": "seed"},
                    created_by="seed",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
                EntityAspect(
                    id="asp-3",
                    urn=URN_DATASET,
                    aspect_name="lineageEdge",
                    version=1,
                    payload=lineage_edge,
                    payload_hash=_hash_payload(lineage_edge),
                    system_metadata={},
                    created_by="seed",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
                EntityAspect(
                    id="asp-4",
                    urn=URN_MODEL,
                    aspect_name="mlModelMetadata",
                    version=1,
                    payload=model_meta,
                    payload_hash=_hash_payload(model_meta),
                    system_metadata={},
                    created_by="seed",
                    owner_user_id=None,
                    workspace_id=None,
                    project_id=None,
                ),
            ]
        )
        session.commit()

    app = FastAPI()
    app.include_router(metadata_aspects.router)
    return TestClient(app)


def test_browse_entities_supports_cursor_and_filters(client: TestClient) -> None:
    response = client.get(
        "/metadata/aspects/entities",
        params={"entity_type": "dataset", "q": "aqp_silver", "limit": 10},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_estimated"] == 1
    assert payload["entries"][0]["urn"] == URN_DATASET
    assert payload["entries"][0]["aspect_counts"]["datasetProperties"] == 2

    page_one = client.get("/metadata/aspects/entities", params={"limit": 1})
    assert page_one.status_code == 200
    next_cursor = page_one.json()["next_cursor"]
    assert isinstance(next_cursor, str)

    page_two = client.get(
        "/metadata/aspects/entities",
        params={"limit": 1, "cursor": next_cursor},
    )
    assert page_two.status_code == 200
    assert len(page_two.json()["entries"]) == 1


def test_get_entity_returns_aspect_counts(client: TestClient) -> None:
    urn = quote(URN_DATASET, safe="")
    response = client.get(f"/metadata/aspects/entities/{urn}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["urn"] == URN_DATASET
    assert payload["aspect_counts"]["datasetProperties"] == 2
    assert payload["aspect_counts"]["lineageEdge"] == 1


def test_get_entity_returns_404_when_missing(client: TestClient) -> None:
    missing = quote("urn:aqp:dataset:prod:missing", safe="")
    response = client.get(f"/metadata/aspects/entities/{missing}")
    assert response.status_code == 404


def test_list_entity_aspects_hides_payload(client: TestClient) -> None:
    urn = quote(URN_DATASET, safe="")
    response = client.get(f"/metadata/aspects/entities/{urn}/aspects")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows[0]["aspect_name"] == "datasetProperties"
    assert "payload" not in rows[0]


def test_aspect_history_returns_full_payload(client: TestClient) -> None:
    urn = quote(URN_DATASET, safe="")
    response = client.get(
        f"/metadata/aspects/entities/{urn}/aspects/datasetProperties/history",
        params={"limit": 2},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entries"][0]["version"] == 2
    assert payload["entries"][0]["payload"]["description"] == "daily bars v2"


def test_get_aspect_by_id_returns_payload(client: TestClient) -> None:
    response = client.get("/metadata/aspects/aspects/asp-2")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == "asp-2"
    assert payload["payload"]["description"] == "daily bars v2"


def test_get_aspect_by_id_returns_404(client: TestClient) -> None:
    response = client.get("/metadata/aspects/aspects/does-not-exist")
    assert response.status_code == 404


def test_lineage_endpoint_returns_structured_graph(client: TestClient) -> None:
    urn = quote(URN_DATASET, safe="")
    response = client.get(
        f"/metadata/aspects/entities/{urn}/lineage",
        params={"depth": 2, "direction": "both"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["lineage"]["entity"] == URN_DATASET
    assert payload["lineage"]["downstream_edges"][0]["to_entity"] == URN_MODEL


def test_distinct_type_endpoints_return_counts(client: TestClient) -> None:
    aspect_types = client.get("/metadata/aspects/aspect-types")
    assert aspect_types.status_code == 200, aspect_types.text
    names = {row["name"] for row in aspect_types.json()}
    assert {"datasetProperties", "lineageEdge", "mlModelMetadata"}.issubset(names)

    entity_types = client.get("/metadata/aspects/entity-types")
    assert entity_types.status_code == 200, entity_types.text
    entity_names = {row["name"] for row in entity_types.json()}
    assert {"dataset", "mlmodel"}.issubset(entity_names)


def test_main_api_includes_metadata_aspects_router() -> None:
    from aqp.api import main as main_mod

    paths = {route.path for route in main_mod.app.routes if hasattr(route, "path")}
    assert any(path.startswith("/metadata/aspects") for path in paths)
