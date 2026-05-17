"""Route tests for local-ingest path mapping."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_pipelines_ingest_maps_windows_host_path(
    tmp_path: Path, monkeypatch
) -> None:
    from aqp.api.routes import data_pipelines
    from aqp.tasks import ingestion_tasks

    host_data = tmp_path / "host-data"
    src_dir = host_data / "sasdata"
    src_dir.mkdir(parents=True)
    (src_dir / "demo.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(
        data_pipelines.settings,
        "local_ingest_path_map",
        f"Z:/UnitTest/HostRoot=>{host_data}",
        raising=False,
    )

    captured: dict[str, object] = {}

    class _FakeAsyncResult:
        id = "task-123"

    class _FakeTask:
        @staticmethod
        def delay(*args):
            captured["args"] = args
            return _FakeAsyncResult()

    monkeypatch.setattr(ingestion_tasks, "ingest_local_path", _FakeTask)

    app = FastAPI()
    app.include_router(data_pipelines.router)
    client = TestClient(app)

    resp = client.post(
        "/pipelines/ingest",
        json={
            "path": r"Z:\UnitTest\HostRoot\sasdata",
            "namespace": "aqp",
            "annotate": True,
        },
    )
    assert resp.status_code == 200, resp.text
    call_args = captured["args"]
    assert str(call_args[0]) == str(src_dir.resolve())
