"""Route tests for the LLM lifecycle endpoints under ``/agentic``."""
from __future__ import annotations

import pytest


@pytest.fixture
def fastapi_test_client():
    fastapi = pytest.importorskip("fastapi.testclient")
    from aqp.api.main import app

    return fastapi.TestClient(app)


def test_models_pull_enqueues_celery_task(fastapi_test_client, monkeypatch):
    from aqp.tasks import llm_tasks

    captured: dict[str, object] = {}

    class _Result:
        id = "task-pull-1"

    class _StubTask:
        def delay(self, name: str, host=None):
            captured["name"] = name
            captured["host"] = host or ""
            return _Result()

    monkeypatch.setattr(llm_tasks, "pull_ollama_model", _StubTask())

    res = fastapi_test_client.post("/agentic/models/pull", json={"name": "llama3.2"})
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"] == "task-pull-1"
    assert captured["name"] == "llama3.2"


def test_models_pull_rejects_empty_name(fastapi_test_client):
    res = fastapi_test_client.post("/agentic/models/pull", json={"name": ""})
    assert res.status_code == 400


def test_models_running_returns_payload(fastapi_test_client, monkeypatch):
    from aqp.llm import ollama_client

    monkeypatch.setattr(
        ollama_client,
        "list_running_models",
        lambda host=None: [
            {"name": "llama3.2", "size": 1024, "digest": "sha:abc", "expires_at": "2026-01-01"},
        ],
    )
    res = fastapi_test_client.get("/agentic/models/running")
    assert res.status_code == 200
    body = res.json()
    assert body["running"][0]["name"] == "llama3.2"


def test_models_delete_calls_client(fastapi_test_client, monkeypatch):
    from aqp.llm import ollama_client

    calls: dict[str, str] = {}

    def _delete(name: str, host=None):
        calls["name"] = name
        return True

    monkeypatch.setattr(ollama_client, "delete_model", _delete)
    res = fastapi_test_client.delete("/agentic/models/llama3.2")
    assert res.status_code == 200
    assert calls["name"] == "llama3.2"
    assert res.json()["deleted"] is True


def test_vllm_profiles_route_returns_summary(fastapi_test_client, monkeypatch):
    from aqp.llm import vllm_runner

    monkeypatch.setattr(
        vllm_runner,
        "serving_summary",
        lambda: {"configured_base_url": "", "docker_available": False, "profiles": []},
    )
    res = fastapi_test_client.get("/agentic/vllm/profiles")
    assert res.status_code == 200
    body = res.json()
    assert body["docker_available"] is False
    assert body["profiles"] == []


def test_vllm_start_404_on_unknown_profile(fastapi_test_client, monkeypatch):
    from aqp.llm import vllm_runner

    monkeypatch.setattr(vllm_runner, "get_profile", lambda name: None)
    res = fastapi_test_client.post(
        "/agentic/vllm/start", json={"profile": "does-not-exist"}
    )
    assert res.status_code == 404


def test_grouping_consolidate_requires_confirm(fastapi_test_client):
    res = fastapi_test_client.post(
        "/datasets/grouping/consolidate",
        json={
            "group_name": "aqp.bars_merged",
            "members": ["aqp.bars_part_1", "aqp.bars_part_2"],
            "dry_run": False,
            "drop_members": True,
            "confirm": False,
        },
    )
    assert res.status_code == 400


def test_grouping_consolidate_dry_run_enqueues_task(fastapi_test_client, monkeypatch):
    from aqp.tasks import ingestion_tasks

    class _Result:
        id = "task-consolidate-1"

    captured: dict[str, object] = {}

    class _StubTask:
        def delay(self, **kwargs):
            captured.update(kwargs)
            return _Result()

    monkeypatch.setattr(ingestion_tasks, "consolidate_iceberg_group", _StubTask())
    res = fastapi_test_client.post(
        "/datasets/grouping/consolidate",
        json={
            "group_name": "aqp.bars_merged",
            "members": ["aqp.bars_part_1", "aqp.bars_part_2"],
            "dry_run": True,
            "drop_members": False,
            "confirm": False,
        },
    )
    assert res.status_code == 200
    assert res.json()["task_id"] == "task-consolidate-1"
    assert captured["dry_run"] is True
    assert captured["group_name"] == "aqp.bars_merged"
    assert captured["members"] == ["aqp.bars_part_1", "aqp.bars_part_2"]


def test_inspect_data_source_route(fastapi_test_client, tmp_path, monkeypatch):
    from aqp.data import parquet_inspector

    class _Stub:
        def to_dict(self):
            return {
                "path": str(tmp_path),
                "exists": True,
                "file_count": 1,
                "total_bytes": 100,
                "sample_files": [],
                "partition_keys": [],
                "columns": ["a"],
                "dtypes": {"a": "int64"},
                "sample_rows": [],
                "suggested_glob": None,
                "suggested_column_map": {},
                "hive_partitioning": False,
                "error": None,
            }

    monkeypatch.setattr(parquet_inspector, "inspect_root", lambda path, max_files=5000: _Stub())
    res = fastapi_test_client.post(
        "/backtest/data-sources/inspect",
        json={"parquet_root": str(tmp_path)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["exists"] is True
    assert body["file_count"] == 1
