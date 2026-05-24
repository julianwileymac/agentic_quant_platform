"""Pipeline metadata emission tests."""

from __future__ import annotations


def test_metadata_disabled_by_default():
    from pipelines.config import PipelineConfig
    from pipelines.metadata import emit_minio_object

    emitted = emit_minio_object(
        PipelineConfig(datahub_enabled=False),
        bucket="pipeline-raw",
        key="sample.json",
    )

    assert emitted is False


def test_metadata_sink_handles_missing_datahub_dependency(monkeypatch):
    from pipelines.config import PipelineConfig
    from pipelines.metadata import emit_pipeline_run

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("datahub"):
            raise ImportError("no datahub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    emitted = emit_pipeline_run(
        PipelineConfig(datahub_enabled=True),
        name="raw-ingest/sample",
    )

    assert emitted is False
