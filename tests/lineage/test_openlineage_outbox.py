"""OpenLineage outbox + relay tests (Workstream B).

Covers:

- :func:`aqp_event_to_openlineage` produces a syntactically valid
  RunEvent (eventType / eventTime / producer / job / run / inputs /
  outputs).
- The :class:`OpenLineageOutboxObserver` writes one row per
  :class:`LineageEvent`.
- :func:`drain_outbox_once` POSTs each pending row, marks ``sent_at``
  on success, increments ``attempts`` + records ``last_error`` on
  failure.
"""
from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def relay_session(in_memory_db, monkeypatch: pytest.MonkeyPatch):
    """Boot the OpenLineage outbox observer in force mode."""
    from aqp.config import settings
    from aqp.lineage.openlineage.observer import (
        register_openlineage_observer,
        unregister_openlineage_observer,
    )

    monkeypatch.setattr(settings, "lineage_openlineage_relay_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "lineage_openlineage_marquez_url", "http://marquez.test:5000", raising=False
    )
    unregister_openlineage_observer()
    register_openlineage_observer(force=True)
    yield
    unregister_openlineage_observer()


def _emit(event_kwargs: dict[str, Any]) -> None:
    from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

    get_lineage_bus().emit(LineageEvent(**event_kwargs))


def test_mapper_returns_minimal_runevent() -> None:
    from aqp.data.catalog.lineage import LineageEvent
    from aqp.lineage.openlineage import aqp_event_to_openlineage

    event = LineageEvent(
        transform_kind="iceberg_append",
        target_table_id="aqp_silver_eq.spy_5m",
        rows_written=42,
        actor="iceberg_catalog",
        actor_kind="service",
        medallion_layer="silver",
        details={"iceberg_snapshot_id": 99},
    )
    payload = aqp_event_to_openlineage(event)
    assert payload["eventType"] == "COMPLETE"
    assert "eventTime" in payload
    assert payload["producer"]
    assert payload["job"]["namespace"] == "aqp"
    assert payload["job"]["name"].startswith("iceberg_append:")
    assert payload["run"]["runId"]
    assert payload["run"]["facets"]["aqp"]["transform_kind"] == "iceberg_append"
    assert payload["run"]["facets"]["aqp"]["iceberg_snapshot_id"] == 99
    assert payload["outputs"]
    assert payload["outputs"][0]["name"] == "aqp_silver_eq.spy_5m"


def test_observer_writes_outbox_row(relay_session) -> None:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_openlineage import OpenLineageOutbox

    _emit(
        {
            "transform_kind": "iceberg_append",
            "target_table_id": "aqp_silver_eq.spy_5m",
            "rows_written": 1,
            "actor": "ingest",
            "actor_kind": "service",
            "medallion_layer": "silver",
        }
    )

    with get_session() as session:
        rows = session.query(OpenLineageOutbox).all()
    assert len(rows) == 1
    assert rows[0].sent_at is None
    assert rows[0].attempts == 0
    assert rows[0].job_namespace == "aqp"
    assert rows[0].job_name.startswith("iceberg_append:")


def test_drain_marks_sent_when_post_succeeds(relay_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.lineage.openlineage import relay as relay_mod
    from aqp.persistence.db import get_session
    from aqp.persistence.models_openlineage import OpenLineageOutbox

    posted: list[dict] = []

    def fake_post(payload):
        posted.append(payload)
        return (True, "200")

    monkeypatch.setattr(relay_mod, "post_openlineage_event", fake_post)

    _emit(
        {
            "transform_kind": "iceberg_append",
            "target_table_id": "ns.t",
            "actor": "x",
            "actor_kind": "service",
        }
    )
    summary = relay_mod.drain_outbox_once(batch=10)
    assert summary["sent"] == 1
    assert summary["failed"] == 0
    assert len(posted) == 1

    with get_session() as session:
        row = session.query(OpenLineageOutbox).one()
    assert row.sent_at is not None
    assert row.last_error is None


def test_drain_records_failure(relay_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.lineage.openlineage import relay as relay_mod
    from aqp.persistence.db import get_session
    from aqp.persistence.models_openlineage import OpenLineageOutbox

    def fake_post(payload):
        return (False, "status=503 body=unavailable")

    monkeypatch.setattr(relay_mod, "post_openlineage_event", fake_post)

    _emit(
        {
            "transform_kind": "iceberg_append",
            "target_table_id": "ns.t",
            "actor": "x",
            "actor_kind": "service",
        }
    )
    summary = relay_mod.drain_outbox_once(batch=10)
    assert summary["sent"] == 0
    assert summary["failed"] == 1

    with get_session() as session:
        row = session.query(OpenLineageOutbox).one()
    assert row.sent_at is None
    assert row.attempts == 1
    assert "503" in (row.last_error or "")


def test_observer_no_op_when_flag_off(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings
    from aqp.lineage.openlineage.observer import (
        register_openlineage_observer,
        unregister_openlineage_observer,
    )
    from aqp.persistence.db import get_session
    from aqp.persistence.models_openlineage import OpenLineageOutbox

    monkeypatch.setattr(settings, "lineage_openlineage_relay_enabled", False, raising=False)
    unregister_openlineage_observer()
    assert register_openlineage_observer() is None

    _emit(
        {
            "transform_kind": "iceberg_append",
            "target_table_id": "ns.t",
            "actor": "x",
            "actor_kind": "service",
        }
    )
    with get_session() as session:
        assert session.query(OpenLineageOutbox).count() == 0


def test_post_returns_error_when_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings
    from aqp.lineage.openlineage.relay import post_openlineage_event

    monkeypatch.setattr(settings, "lineage_openlineage_marquez_url", "", raising=False)
    ok, info = post_openlineage_event({"hello": "world"})
    assert not ok
    assert "marquez_url_not_configured" in info
