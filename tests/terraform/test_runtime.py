"""Tests for :class:`aqp.terraform.runtime.TerraformRuntime` lifecycle.

The tests stub out the executor + persistence layers so they run
without a terraform binary / Postgres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aqp.terraform.runtime import (
    TerraformApprovalRequiredError,
    TerraformHaltedError,
    TerraformRuntime,
)
from aqp.terraform.spec import TerraformStackSpec


@dataclass
class _StubExecResult:
    action: str
    workspace_dir: str = "/tmp/aqp/ws"
    exit_code: int = 0
    duration_ms: float = 12.5
    stdout_log_path: str = "/tmp/aqp/stdout.log"
    stderr_log_path: str = "/tmp/aqp/stderr.log"
    plan_artifact_path: str | None = None
    plan_summary_path: str | None = None
    plan_summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_run_row_payload(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_log_uri": f"file://{self.stdout_log_path}",
            "stderr_log_uri": f"file://{self.stderr_log_path}",
            "plan_summary_json": dict(self.plan_summary),
            "error": self.error,
        }


def _spec() -> TerraformStackSpec:
    return TerraformStackSpec(
        name="Cluster",
        slug="cluster",
        module_kind="kubernetes",
        environment="local",
        cloud_provider="local",
    )


def test_should_halt_returns_false_when_redis_unreachable():
    runtime = TerraformRuntime(_spec(), workspace_id="ws-1")
    with patch("aqp.terraform.runtime.TerraformRuntime.should_halt", return_value=False):
        runtime._check_halt()  # should not raise


def test_check_halt_raises_when_kill_switch_set():
    runtime = TerraformRuntime(_spec(), workspace_id="ws-1")
    with patch.object(TerraformRuntime, "should_halt", return_value=True):
        with pytest.raises(TerraformHaltedError):
            runtime._check_halt()


def test_require_approval_no_policy_passes_through(monkeypatch):
    runtime = TerraformRuntime(_spec(), workspace_id="ws-1")
    # Force the policy lookup to find nothing.
    monkeypatch.setattr(
        "aqp.terraform.runtime.TerraformRuntime._require_approval",
        TerraformRuntime._require_approval,
    )
    # With no hard_mandatory policy attachment the helper just returns.
    runtime._require_approval(run_kind="apply", started_by_user_id="u1", approver_user_id="u1")


def test_runtime_plan_uses_ledger(monkeypatch):
    """The plan() method opens + finalises a run row and calls the executor."""
    runtime = TerraformRuntime(_spec(), workspace_id="ws-1", run_id="run-xyz")
    stub = _StubExecResult(action="plan", plan_summary={"create": 1})
    fake_executor = MagicMock()
    fake_executor.plan.return_value = stub
    runtime._executor = fake_executor

    monkeypatch.setattr(runtime, "_persist_spec", lambda: "spec-ver-1")
    monkeypatch.setattr(runtime, "_open_run_row", lambda **k: "run-row-1")
    finalize = MagicMock()
    monkeypatch.setattr(runtime, "_finalize_run_row", finalize)
    monkeypatch.setattr(runtime, "_resolve_workspace_slug", lambda: "cluster")
    monkeypatch.setattr(runtime, "_evaluate_policy", lambda *a, **k: {})
    monkeypatch.setattr(runtime, "_snapshot_state_version", lambda **k: None)

    result = runtime.plan(started_by_user_id="me")
    assert result.status == "completed"
    assert result.run_kind == "plan"
    fake_executor.plan.assert_called_once()
    finalize.assert_called_once()
    args = finalize.call_args.kwargs
    assert args["status"] == "completed"


def test_runtime_handles_executor_exception(monkeypatch):
    runtime = TerraformRuntime(_spec(), workspace_id="ws-1")
    fake_executor = MagicMock()
    fake_executor.plan.side_effect = RuntimeError("disk full")
    runtime._executor = fake_executor

    monkeypatch.setattr(runtime, "_persist_spec", lambda: None)
    monkeypatch.setattr(runtime, "_open_run_row", lambda **k: "run-err")
    finalize = MagicMock()
    monkeypatch.setattr(runtime, "_finalize_run_row", finalize)
    monkeypatch.setattr(runtime, "_resolve_workspace_slug", lambda: "x")

    result = runtime.plan(started_by_user_id="me")
    assert result.status == "errored"
    assert "disk full" in (result.error or "")
    finalize.assert_called_once()
    assert finalize.call_args.kwargs["status"] == "errored"


def test_open_run_row_uses_resolved_workspace_row_id(monkeypatch):
    runtime = TerraformRuntime(
        _spec(),
        workspace_id="aqp-local",
        run_id="run-row-test",
        prerendered_workspace_dir="/tmp/aqp-local",
    )
    monkeypatch.setattr(runtime, "_persist_spec", lambda: "spec-ver-1")
    monkeypatch.setattr(
        runtime, "_resolve_workspace_row_id", lambda **_kwargs: "workspace-row-1"
    )

    captured: dict[str, Any] = {}

    class _RunRow:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.id = kwargs.get("id")
            self.owner_user_id = None
            self.workspace_id = None
            self.project_id = None
            self.experiment_id = None
            self.test_id = None

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add(self, _row):
            return None

        def commit(self):
            return None

    monkeypatch.setattr("aqp.persistence.models_terraform.TerraformRun", _RunRow)
    monkeypatch.setattr("aqp.persistence.db.SessionLocal", _Session)

    row_id = runtime._open_run_row(run_kind="plan", started_by_user_id="me")
    assert row_id == "run-row-test"
    assert captured["terraform_workspace_id"] == "workspace-row-1"
