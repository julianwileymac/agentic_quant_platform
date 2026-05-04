"""Tests for data layer control expansion contracts."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def test_ingest_path_exposes_director_controls(tmp_path: Path, monkeypatch) -> None:
    from aqp.api.routes.data_pipelines import IngestPathRequest, ingest_path
    from aqp.tasks import ingestion_tasks

    source = tmp_path / "sample.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    class _FakeDelay:
        id = "task-director-controls"

    class _FakeTask:
        @staticmethod
        def delay(*args: Any) -> _FakeDelay:
            captured["args"] = args
            return _FakeDelay()

    monkeypatch.setattr(ingestion_tasks, "ingest_local_path", _FakeTask)

    result = ingest_path(
        IngestPathRequest(
            path=str(source),
            namespace="aqp_test",
            table_prefix="demo",
            annotate=False,
            max_rows_per_dataset=10,
            max_files_per_dataset=2,
            director_enabled=False,
            allowed_namespaces=["aqp_test"],
        )
    )

    assert result.task_id == "task-director-controls"
    assert captured["args"][-2:] == (False, ["aqp_test"])


def test_import_source_persists_metadata_snapshot(monkeypatch) -> None:
    from aqp.api.routes import sources

    captured: dict[str, Any] = {}

    def _fake_upsert(**kwargs: Any) -> dict[str, Any]:
        captured["upsert"] = kwargs
        return {
            "id": "source-1",
            "name": kwargs["name"],
            "display_name": kwargs["display_name"],
            "kind": kwargs["kind"],
            "vendor": kwargs["vendor"],
            "auth_type": kwargs["auth_type"],
            "base_url": kwargs["base_url"],
            "protocol": kwargs["protocol"],
            "capabilities": kwargs["capabilities"],
            "rate_limits": kwargs["rate_limits"] or {},
            "credentials_ref": kwargs["credentials_ref"],
            "enabled": True,
            "meta": kwargs["meta"],
            "created_at": sources.datetime.utcnow(),
            "updated_at": sources.datetime.utcnow(),
        }

    def _fake_persist(**kwargs: Any) -> dict[str, Any]:
        captured["persist"] = kwargs
        return {}

    monkeypatch.setattr(sources, "upsert_data_source", _fake_upsert)
    monkeypatch.setattr(sources, "_persist_source_library", _fake_persist)

    row = sources.import_source(
        sources.SourceImportRequest(
            name="Vendor Feed",
            raw_source_url="https://example.com/feed.csv",
            display_name="Vendor Feed",
            tags=["vendor"],
        )
    )

    assert row.name == "vendor_feed"
    assert captured["upsert"]["capabilities"]["pipelines"]["default_node"] == "source.http"
    assert captured["persist"]["change_kind"] == "import"


def test_airbyte_metadata_sync_is_metadata_only(monkeypatch) -> None:
    from aqp.tasks import data_metadata_tasks as tasks
    import aqp.services.airbyte_client as airbyte_client
    import aqp.data.sources.registry as registry

    calls: list[str] = []
    persisted_sources: list[dict[str, Any]] = []
    persisted_configs: list[dict[str, Any]] = []

    class _FakeAirbyteClient:
        def list_workspaces(self) -> dict[str, Any]:
            calls.append("list_workspaces")
            return {"workspaces": [{"id": "workspace-1"}]}

        def list_sources(self) -> dict[str, Any]:
            calls.append("list_sources")
            return {"sources": [{"sourceId": "src-1", "name": "Demo"}]}

        def list_destinations(self) -> dict[str, Any]:
            calls.append("list_destinations")
            return {"destinations": [{"destinationId": "dst-1", "name": "Lake"}]}

        def list_connections(self) -> dict[str, Any]:
            calls.append("list_connections")
            return {"connections": [{"connectionId": "conn-1", "name": "Demo Load", "schedule": {"cron": "0 * * * *"}}]}

        def discover_source_schema(self, source_id: str) -> dict[str, Any]:
            calls.append(f"discover:{source_id}")
            return {"catalog": {"streams": [{"stream": {"name": "records"}}]}}

        def trigger_sync(self, connection_id: str) -> dict[str, Any]:  # pragma: no cover - must not be called
            raise AssertionError(f"trigger_sync should not be called: {connection_id}")

    def _fake_upsert(**kwargs: Any) -> dict[str, Any]:
        persisted_sources.append(kwargs)
        return {
            "id": "source-1",
            "name": kwargs["name"],
            "display_name": kwargs["display_name"],
        }

    monkeypatch.setattr(airbyte_client, "AirbyteClient", _FakeAirbyteClient)
    monkeypatch.setattr(registry, "upsert_data_source", _fake_upsert)
    monkeypatch.setattr(tasks, "_persist_source_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(tasks, "_persist_dataset_pipeline_config", lambda **kwargs: persisted_configs.append(kwargs))

    result = tasks._sync_airbyte_metadata(discover_schemas=True, enrich=False)

    assert result["sources"] == 1
    assert "list_connections" in calls
    assert "discover:src-1" in calls
    assert persisted_sources[0]["name"] == "airbyte_demo"
    assert persisted_configs[0]["config"]["metadata_only"] is True
