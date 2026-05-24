"""Dagster DataHub orchestration asset tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from dagster import Failure

from pipelines.dagster_user_code import datahub_assets

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _Context:
    op_config = {
        "namespace": "mlops",
        "job_suffix": "test",
        "wait_for_completion": True,
        "timeout_seconds": 123,
    }

    def __init__(self) -> None:
        self.metadata = None

    def add_output_metadata(self, metadata):
        self.metadata = metadata


def test_run_datahub_group_submits_argo_template(monkeypatch):
    calls = {}

    def fake_submit(**kwargs):
        calls.update(kwargs)
        return {"status": "succeeded", "workflow_name": "datahub-ingestion-test"}

    monkeypatch.setattr(
        datahub_assets,
        "submit_argo_workflow_from_template",
        fake_submit,
    )

    context = _Context()
    result = datahub_assets._run_datahub_group(context, "mlflow")

    assert result["status"] == "succeeded"
    assert calls["template_name"] == "datahub-ingestion"
    assert calls["namespace"] == "mlops"
    assert calls["parameters"] == {
        "source_group": "mlflow",
        "job_suffix": "test",
        "timeout_seconds": "123",
    }
    assert context.metadata is not None


def test_run_datahub_group_raises_on_failed_workflow(monkeypatch):
    def fake_submit(**kwargs):
        return {"status": "failed", "workflow_name": "datahub-ingestion-test"}

    monkeypatch.setattr(
        datahub_assets,
        "submit_argo_workflow_from_template",
        fake_submit,
    )

    with pytest.raises(Failure):
        datahub_assets._run_datahub_group(_Context(), "platform")


def test_datahub_source_groups_exclude_agentic_assistants():
    workflow_template = (
        _REPO_ROOT
        / "kubernetes"
        / "mlops"
        / "pipelines"
        / "workflowtemplate-datahub-ingestion.yaml"
    ).read_text()
    kustomization = (
        _REPO_ROOT
        / "kubernetes"
        / "base-services"
        / "datahub"
        / "kustomization.yaml"
    ).read_text()

    assert "datahub-ingest-agentic-assistants" not in workflow_template
    assert "cronjob-ingest-agentic-assistants" not in kustomization
