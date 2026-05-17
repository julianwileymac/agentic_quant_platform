from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import feeds

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

    monkeypatch.setattr(feeds, "get_session", _patched_get_session)
    app = FastAPI()
    app.include_router(feeds.router, prefix="/api/v1/feeds")
    return TestClient(app)


def test_list_feeds_returns_paginated(client: TestClient, in_memory_db) -> None:
    from aqp.persistence.models import DataSource

    Session = in_memory_db
    with Session() as session:
        session.add_all(
            [
                DataSource(
                    id="feed-a",
                    name="feed-a",
                    display_name="Feed A",
                    kind="rest_api",
                    auth_type="none",
                    protocol="https/json",
                    credentials_ref="AQP_FEED_A_TOKEN",
                    enabled=True,
                ),
                DataSource(
                    id="feed-b",
                    name="feed-b",
                    display_name="Feed B",
                    kind="rest_api",
                    auth_type="none",
                    protocol="https/json",
                    credentials_ref=None,
                    enabled=True,
                ),
                DataSource(
                    id="feed-c",
                    name="feed-c",
                    display_name="Feed C",
                    kind="rest_api",
                    auth_type="none",
                    protocol="https/json",
                    credentials_ref="AQP_FEED_C_TOKEN",
                    enabled=False,
                ),
            ]
        )
        session.commit()

    response = client.get("/api/v1/feeds/", params={"limit": 10, "offset": 0})
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 3
    by_name = {row["name"]: row for row in rows}
    assert by_name["feed-a"]["credentials_configured"] is True
    assert by_name["feed-a"]["credentials_ref"] == "<configured>"
    assert by_name["feed-b"]["credentials_configured"] is False
    assert by_name["feed-b"]["credentials_ref"] is None


def test_create_feed_validates_loader_class_path(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/feeds/",
        json={
            "name": "bad-loader-feed",
            "loader_class_path": "nonexistent.module.Class",
        },
    )
    assert bad.status_code == 400

    good = client.post(
        "/api/v1/feeds/",
        json={
            "name": "good-loader-feed",
            "loader_class_path": "json.decoder.JSONDecoder",
        },
    )
    assert good.status_code == 201, good.text
    payload = good.json()
    assert payload["name"] == "good-loader-feed"
    assert payload["loader_class_path"] == "json.decoder.JSONDecoder"


def test_create_feed_publishes_event(client: TestClient) -> None:
    from aqp.data.mcp.event_bus import FeedEvent, get_feed_event_bus

    seen: list[FeedEvent] = []
    unsubscribe = get_feed_event_bus().subscribe(lambda event: seen.append(event))
    try:
        response = client.post(
            "/api/v1/feeds/",
            json={"name": "evented-feed"},
        )
    finally:
        unsubscribe()

    assert response.status_code == 201, response.text
    assert len(seen) == 1
    assert seen[0].kind == "upsert"
    assert seen[0].data_source_id


def test_soft_delete_sets_is_enabled_false(client: TestClient, in_memory_db) -> None:
    from aqp.persistence.models import DataSource

    Session = in_memory_db
    with Session() as session:
        row = DataSource(
            id="feed-delete",
            name="feed-delete",
            display_name="Delete Feed",
            kind="rest_api",
            auth_type="none",
            protocol="https/json",
            enabled=True,
        )
        session.add(row)
        session.commit()

    deleted = client.delete("/api/v1/feeds/feed-delete")
    assert deleted.status_code == 204, deleted.text

    fetched = client.get("/api/v1/feeds/feed-delete")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["is_enabled"] is False
