from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import instrument_catalog

    Session = in_memory_db

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

    monkeypatch.setattr(instrument_catalog, "get_session", _patched_get_session)
    app = FastAPI()
    app.include_router(instrument_catalog.router, prefix="/api/v1/instruments")
    return TestClient(app)


def test_list_instruments_filter_by_asset_class(
    client: TestClient,
    in_memory_db,
) -> None:
    from aqp.persistence.models_instrument_catalog import InstrumentCatalog

    Session = in_memory_db
    with Session() as session:
        session.add_all(
            [
                InstrumentCatalog(
                    id="inst-1",
                    universal_ticker="AAPL",
                    asset_class="equity",
                    exchange_code="NASDAQ",
                    metadata_blob={"summary": "Apple equity"},
                    content_hash="hash-1",
                    schema_version=1,
                ),
                InstrumentCatalog(
                    id="inst-2",
                    universal_ticker="BTCUSD",
                    asset_class="cryptocurrency",
                    exchange_code="COINBASE",
                    metadata_blob={"summary": "Bitcoin spot"},
                    content_hash="hash-2",
                    schema_version=1,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/instruments/", params={"asset_class": "equity"})
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["asset_class"] == "equity"


def test_get_one_returns_metadata_blob(client: TestClient, in_memory_db) -> None:
    from aqp.persistence.models_instrument_catalog import InstrumentCatalog

    Session = in_memory_db
    with Session() as session:
        session.add(
            InstrumentCatalog(
                id="inst-meta",
                universal_ticker="MSFT",
                asset_class="equity",
                exchange_code="NASDAQ",
                metadata_blob={"summary": "Microsoft", "sector": "technology"},
                content_hash="hash-meta",
                schema_version=1,
            )
        )
        session.commit()

    response = client.get("/api/v1/instruments/inst-meta")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == "inst-meta"
    assert payload["metadata_blob"]["summary"] == "Microsoft"
    assert payload["metadata_blob"]["sector"] == "technology"


def test_post_sync_returns_task_id(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import aqp.tasks.instrument_catalog_tasks as task_mod

    class _FakeResult:
        id = "abc"

    class _FakeTask:
        def delay(self, *, batch_size: int) -> _FakeResult:
            assert batch_size == 123
            return _FakeResult()

    # Replace the module-level task object so the route's
    # `from ... import sync_finance_database` resolves to the fake.
    monkeypatch.setattr(task_mod, "sync_finance_database", _FakeTask())

    response = client.post("/api/v1/instruments/sync", json={"batch_size": 123})
    assert response.status_code == 200, response.text
    assert response.json()["task_id"] == "abc"
