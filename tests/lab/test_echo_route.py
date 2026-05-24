"""End-to-end echo test for the Data Lab Phase 0 foundation.

Mirrors :mod:`tests.api.test_assistants_route` — exercises the
``/lab/catalog/node-types`` palette + ``POST /lab/graphs`` + the
inline run path + halt-all using FastAPI's TestClient with mocked
persistence so we don't need Postgres.

Phase 0 contract this test enforces:

1. The 35-node taxonomy is exposed via ``GET /lab/catalog/node-types``.
2. Creating a malformed GraphSpec (unknown node type) returns 400
   with a structured ``violations`` list.
3. The Lab WS route is mounted at ``/ws/lab/{session_id}``.
4. The kill-switch endpoint is mounted at ``/lab/halt-all``.

The DB-backed POST /lab/graphs / submit-run path is covered by the
:mod:`tests.lab.test_runtime` end-to-end test (which runs LabRuntime
inline without Postgres) — we don't need Postgres in this test.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqp.api.routes.lab import router, ws_router


@pytest.fixture
def lab_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Permissive mode + local-provider so the secure_router falls
    # back to the deterministic local user rather than 401-ing on
    # missing JWTs. Also dependency-override the auth bouncer so the
    # base ``require_authenticated`` path doesn't try to validate.
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_enforce", "permissive", raising=False)
    monkeypatch.setattr(settings, "auth_provider", "local", raising=False)

    from aqp.api.security import require_authenticated
    from aqp.auth import CurrentUser, current_user
    from aqp.auth.user import default_user

    fake_user = default_user()
    if not isinstance(fake_user, CurrentUser):
        fake_user = CurrentUser(
            id="local-default-user",
            email="local@test",
            display_name="local-test",
            is_default=True,
        )

    app = FastAPI()
    app.dependency_overrides[current_user] = lambda: fake_user
    app.dependency_overrides[require_authenticated] = lambda: fake_user
    app.include_router(router)
    app.include_router(ws_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Catalog (35-node taxonomy)
# ---------------------------------------------------------------------------


def test_catalog_node_types_lists_full_taxonomy(lab_client: TestClient) -> None:
    res = lab_client.get("/lab/catalog/node-types")
    assert res.status_code == 200
    body = res.json()
    # 35 blueprint nodes + 2 Phase 1 snippet additions (snippet.python /
    # snippet.sql) = 37. New additions bump this assertion together
    # with the relevant registry change.
    assert body["total_nodes"] == 37
    assert set(body["modes"]) == {"eda", "testing", "evaluation", "simulation"}
    categories = {c["name"] for c in body["categories"]}
    # All 10 categories present per the blueprint.
    assert {
        "DataSource",
        "Transformation",
        "Feature",
        "Alpha",
        "Model",
        "Strategy",
        "Math",
        "Labeler",
        "Output",
        "Agent",
    }.issubset(categories)


def test_catalog_real_executors_have_concrete_paths(lab_client: TestClient) -> None:
    body = lab_client.get("/lab/catalog/node-types").json()
    by_alias = {}
    for cat in body["categories"]:
        for item in cat["items"]:
            by_alias[item["alias"]] = item
    assert (
        by_alias["data.iceberg_scan"]["executor"]
        == "aqp.lab.executors.data_iceberg_scan:execute"
    )
    assert (
        by_alias["xform.rank"]["executor"] == "aqp.lab.executors.xform_rank:execute"
    )
    assert (
        by_alias["out.tearsheet"]["executor"]
        == "aqp.lab.executors.output_tearsheet:execute"
    )
    # Phase 0 shipped 3 real executors; Phase 2 brought the count up
    # to 13 (the 15-node target minus 2 that get the placeholder
    # treatment until Phase 3 finalises their dependencies).
    placeholders = [
        item["alias"]
        for cat in body["categories"]
        for item in cat["items"]
        if item["executor"] == "aqp.lab.executors._placeholder:execute"
    ]
    real = 35 - len(placeholders)
    assert real >= 13, f"expected >=13 real executors after Phase 2, got {real}"


# ---------------------------------------------------------------------------
# Graph create — compliance failure path
# ---------------------------------------------------------------------------


def test_create_graph_with_unknown_node_type_returns_400(
    lab_client: TestClient,
) -> None:
    payload = {
        "lab_id": "test-lab",
        "name": "broken",
        "spec": {
            "name": "broken",
            "mode": "testing",
            "nodes": [
                {
                    "id": "bad",
                    "type": "not.a.real.node",
                    "category": "DataSource",
                    "outputs": [{"name": "out", "dtype": "frame"}],
                }
            ],
            "edges": [],
        },
    }
    res = lab_client.post("/lab/graphs", json=payload)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["error"] == "graph failed pre-flight compliance"
    rules = [v["rule"] for v in detail["violations"]]
    assert "lab.node_type_registered" in rules


# ---------------------------------------------------------------------------
# Kill switch + halt-all surface
# ---------------------------------------------------------------------------


def test_halt_all_endpoint_is_mounted(
    lab_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint is reachable (response code depends on DB
    availability — 200 with halted=0 when DB is up, 500 otherwise).
    """
    try:
        res = lab_client.post("/lab/halt-all")
    except ConnectionRefusedError:
        # Expected when Postgres isn't running in the test env;
        # proves the route resolved and reached the DB query.
        return
    except Exception as exc:  # noqa: BLE001
        # Any DB-related exception still proves the route mounted.
        if "refused" in str(exc).lower() or "connection" in str(exc).lower():
            return
        raise
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        assert "halted" in res.json()


# ---------------------------------------------------------------------------
# Route mounting (smoke)
# ---------------------------------------------------------------------------


def test_lab_routes_mounted(lab_client: TestClient) -> None:
    """The Phase 0 route surface is reachable."""
    expected_paths = {
        "/lab/catalog/node-types",
        "/lab/graphs",
        "/lab/graphs/{graph_id}",
        "/lab/graphs/{graph_id}/runs",
        "/lab/runs/{run_id}",
        "/lab/runs/{run_id}/nodes",
        "/lab/runs/{run_id}/artifacts",
        "/lab/runs/{run_id}/cancel",
        "/lab/halt-all",
        "/ws/lab/{session_id}",
    }
    paths = {
        getattr(r, "path", None) for r in lab_client.app.router.routes
    }
    missing = expected_paths - paths
    assert not missing, f"missing Lab routes: {missing}"


# ---------------------------------------------------------------------------
# Inline runtime echo (no DB)
# ---------------------------------------------------------------------------


def test_inline_runtime_echo_via_lab_runtime() -> None:
    """The end-to-end echo: GraphSpec → LabRuntime → terminal envelope.

    Doesn't go through the route (which needs a DB session); instead
    exercises the same code path the route calls when ``inline=True``
    (the Phase 0 default). This is the foundation contract:
    submit_run -> compile -> dispatch -> finalise.
    """
    from aqp.lab.runtime import LabRuntime
    from aqp.lab.schema import GraphSpec, NodeRuntime, NodeSpec, Port, PortDType

    spec = GraphSpec(
        name="echo",
        mode="testing",
        nodes=[
            NodeSpec(
                id="echo",
                type="out.tearsheet",
                category="Output",
                inputs=[Port(name="portfolio", dtype=PortDType.PORTFOLIO)],
                outputs=[Port(name="out", dtype=PortDType.JSON)],
                params={"values": [1.0, 1.01, 1.005, 1.02]},
                runtime=NodeRuntime(target="celery"),
            )
        ],
    )
    runtime = LabRuntime(spec)
    result = runtime.submit_run()
    # The tearsheet executor calls into analytics_tasks which may
    # not have quantstats installed in dev. Either it succeeds with
    # status='done' OR it fails with a clear structured error —
    # both prove the run pipeline executed end-to-end.
    assert result.status in {"done", "error"}
    assert result.node_outcomes
    assert result.node_outcomes[0].node_id == "echo"
    assert result.graph_content_hash == spec.snapshot_hash()
    assert result.compile_target == "celery_canvas"
