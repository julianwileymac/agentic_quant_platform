"""CP-native TerraformRuntime contract tests (rule-42 relocation)."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from aqp_platform_core.models.terraform import (
    TerraformRunKind,
    TerraformRunStatus,
    TerraformStackSpec,
)

from aqp_cp.terraform.runtime import (
    TerraformExecutor,
    TerraformRequestContext,
    TerraformRuntime,
    workload_action_for,
    run_status_to_workload_status,
)


class TestTerraformStackSpec:
    def test_compute_hash_is_deterministic(self) -> None:
        spec_a = TerraformStackSpec(
            stack_name="aqp-cluster",
            workspace_id="prod",
            hcl_modules={"main.tf": "output {value=1}"},
        )
        spec_b = TerraformStackSpec(
            stack_name="aqp-cluster",
            workspace_id="prod",
            hcl_modules={"main.tf": "output {value=1}"},
        )
        assert spec_a.compute_hash() == spec_b.compute_hash()

    def test_compute_hash_changes_with_content(self) -> None:
        a = TerraformStackSpec(
            stack_name="x", workspace_id="y", hcl_modules={"m.tf": "a"}
        )
        b = TerraformStackSpec(
            stack_name="x", workspace_id="y", hcl_modules={"m.tf": "b"}
        )
        assert a.compute_hash() != b.compute_hash()


class TestTerraformExecutor:
    def test_render_workspace_writes_files(self, tmp_path: Path) -> None:
        executor = TerraformExecutor(workspaces_dir=str(tmp_path))
        spec = TerraformStackSpec(
            stack_name="aqp-cluster",
            workspace_id="prod",
            hcl_modules={
                "main.tf": "output {value=1}",
                "modules/foo/foo.tf": "variable {default=2}",
            },
            variables={"region": "us-east-1"},
            providers_lock="// pinned",
        )
        ws = executor.render_workspace(spec)
        assert (ws / "main.tf").read_text() == "output {value=1}"
        assert (ws / "modules" / "foo" / "foo.tf").exists()
        assert (ws / ".terraform.lock.hcl").read_text() == "// pinned"
        tfvars = (ws / "terraform.tfvars.json").read_text()
        assert "us-east-1" in tfvars

    def test_render_rejects_traversal(self, tmp_path: Path) -> None:
        executor = TerraformExecutor(workspaces_dir=str(tmp_path))
        spec = TerraformStackSpec(
            stack_name="x",
            workspace_id="y",
            hcl_modules={"../escape.tf": ""},
        )
        with pytest.raises(Exception):
            executor.render_workspace(spec)


class TestTerraformRuntimeHaltGate:
    def test_apply_rejected_when_killswitch_set(
        self, tmp_path: Path
    ) -> None:
        kill_path = tmp_path / "ks"
        executor = TerraformExecutor(workspaces_dir=str(tmp_path / "ws"))
        runtime = TerraformRuntime(executor=executor, kill_switch_path=str(kill_path))
        runtime.halt(reason="testing")
        spec = TerraformStackSpec(
            stack_name="x", workspace_id="y", hcl_modules={"m.tf": ""}
        )
        ctx = TerraformRequestContext(user_id="auth0|x")
        result = asyncio.run(runtime.execute(spec=spec, kind=TerraformRunKind.APPLY, ctx=ctx))
        assert result.status == TerraformRunStatus.REJECTED
        assert result.halt_reason == "kill-switch"

    def test_plan_runs_even_when_killswitch_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kill_path = tmp_path / "ks"
        executor = TerraformExecutor(workspaces_dir=str(tmp_path / "ws"))
        runtime = TerraformRuntime(executor=executor, kill_switch_path=str(kill_path))
        runtime.halt()

        def _fake(spec, kind, extra_args):  # type: ignore[no-untyped-def]
            return 0, "Plan: 1 to add, 0 to change, 0 to destroy.", ""

        monkeypatch.setattr(runtime, "_execute_sync", _fake)
        spec = TerraformStackSpec(
            stack_name="x", workspace_id="y", hcl_modules={"m.tf": ""}
        )
        ctx = TerraformRequestContext(user_id="auth0|x")
        result = asyncio.run(
            runtime.execute(spec=spec, kind=TerraformRunKind.PLAN, ctx=ctx)
        )
        assert result.status == TerraformRunStatus.SUCCEEDED
        assert result.plan_summary.get("add") == 1


class TestActionMapping:
    def test_action_for_apply_is_terraform_apply(self) -> None:
        from aqp_platform_core.models.workloads import WorkloadAction

        assert workload_action_for(TerraformRunKind.APPLY) == WorkloadAction.TERRAFORM_APPLY
        assert workload_action_for(TerraformRunKind.DESTROY) == WorkloadAction.TERRAFORM_DESTROY

    def test_status_projection(self) -> None:
        from aqp_platform_core.models.workloads import WorkloadRunStatus

        assert run_status_to_workload_status(TerraformRunStatus.SUCCEEDED) == WorkloadRunStatus.SUCCEEDED
        assert run_status_to_workload_status(TerraformRunStatus.REJECTED) == WorkloadRunStatus.REJECTED
