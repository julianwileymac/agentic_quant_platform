from __future__ import annotations

import httpx
import pytest


@pytest.fixture
def trino_factory():
    from aqp.services.trino_client import TrinoClient

    def _factory(handler):
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        return TrinoClient(base_url="http://trino:8080", client=client)

    return _factory


def _statement_response(query_id: str, *, columns, rows, next_uri=None):
    payload = {
        "id": query_id,
        "columns": [{"name": col} for col in columns],
        "data": rows,
        "stats": {"state": "FINISHED"},
    }
    if next_uri:
        payload["nextUri"] = next_uri
    return httpx.Response(200, json=payload)


def test_query_aggregates_rows_until_finished(trino_factory):
    pages = iter(
        [
            _statement_response(
                "q1",
                columns=["Catalog"],
                rows=[["iceberg"]],
                next_uri="http://trino:8080/v1/statement/q1/2",
            ),
            _statement_response(
                "q1",
                columns=["Catalog"],
                rows=[["system"]],
            ),
        ]
    )

    def handler(request):
        if request.method == "POST" and request.url.path == "/v1/statement":
            return next(pages)
        if request.method == "GET":
            return next(pages)
        return httpx.Response(404)

    with trino_factory(handler) as client:
        result = client.query("SHOW CATALOGS")

    assert result.state == "FINISHED"
    assert result.columns == ["Catalog"]
    assert [row[0] for row in result.rows] == ["iceberg", "system"]


def test_show_catalogs_uses_query(trino_factory):
    def handler(request):
        return _statement_response("q-catalogs", columns=["Catalog"], rows=[["iceberg"], ["system"]])

    with trino_factory(handler) as client:
        catalogs = client.show_catalogs()

    assert catalogs == ["iceberg", "system"]


def test_verify_marks_iceberg_ok_when_listed(trino_factory, monkeypatch):
    from aqp.services import trino_client

    monkeypatch.setattr(
        trino_client,
        "probe_trino_coordinator",
        lambda timeout_seconds=5.0: {"ok": True, "node_id": "n1", "node_version": "470"},
    )
    schemas_called = {"value": False}

    def handler(request):
        if request.method == "POST" and request.url.path == "/v1/statement":
            statement = request.content.decode()
            if statement == "SHOW CATALOGS":
                return _statement_response("q1", columns=["Catalog"], rows=[["iceberg"]])
            if statement == "SHOW SCHEMAS FROM iceberg":
                schemas_called["value"] = True
                return _statement_response(
                    "q2", columns=["Schema"], rows=[["aqp"], ["information_schema"]]
                )
        return httpx.Response(404)

    with trino_factory(handler) as client:
        verification = client.verify(iceberg_catalog="iceberg")

    assert verification.coordinator_ok is True
    assert verification.query_ok is True
    assert verification.iceberg_catalog_ok is True
    assert verification.iceberg_schemas == ["aqp", "information_schema"]
    assert schemas_called["value"] is True


def test_query_history_parses_payload(trino_factory):
    def handler(request):
        if request.method == "GET" and request.url.path == "/v1/query":
            return httpx.Response(
                200,
                json=[
                    {
                        "queryId": "20260504_001",
                        "state": "FAILED",
                        "user": "aqp",
                        "query": "SELECT 1",
                        "queryStats": {"elapsedTime": "1.50s", "queuedTime": "0.20s"},
                        "errorCode": {"name": "USER_ERROR"},
                        "createTime": "2026-05-04T20:00:00Z",
                    }
                ],
            )
        return httpx.Response(404)

    with trino_factory(handler) as client:
        rows = client.query_history(limit=5)

    assert len(rows) == 1
    row = rows[0]
    assert row.query_id == "20260504_001"
    assert row.state == "FAILED"
    assert row.error == "USER_ERROR"
    assert row.elapsed_seconds == pytest.approx(1.5)
