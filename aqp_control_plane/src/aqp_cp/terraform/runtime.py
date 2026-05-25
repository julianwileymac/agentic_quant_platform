"""CP-native TerraformRuntime — owns plan / apply / destroy lifecycle.

The runtime composes:

- :class:`TerraformExecutor` — the only place that calls
  ``subprocess.run(["terraform", ...])`` directly (rule 42's
  ``aqp_cp.terraform.runner.TerraformExecutor`` invariant).
- :class:`aqp_platform_core.runtime.workload.WorkloadRuntime` — owns
  the ``workload_runs`` audit row + halt fan-out. ``TerraformRun``
  rows are reflected onto ``workload_runs`` with
  ``WorkloadAction.TERRAFORM_*`` so the existing ``workload_runs``
  consumers light up unchanged.
- :class:`aqp_platform_core.runtime.progress.ProgressEmitter` — the
  emitter that publishes canonical AGENTS-rule-4 frames. The AQP-side
  broker injects a Redis-backed emitter; the CP sidecar uses the
  structured log emitter.
- :class:`AuditSink` — optional secondary sink for the
  ``terraform_runs`` ORM table inside the monolith. The
  :class:`aqp_cp.services.audit.HttpAuditSink` (Phase 0.4 todo)
  reuses the M2M token broker to POST every row to
  ``/_internal/audit/terraform-runs``.

The runtime stays small and synchronous in spirit — heavy I/O lives
in the executor. The interesting code is the ``plan -> approval ->
apply`` orchestration and the kill-switch hook.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aqp_platform_core.models.terraform import (
    TerraformRunKind,
    TerraformRunResult,
    TerraformRunStatus,
    TerraformStackSpec,
    TerraformStateBackend,
)
from aqp_platform_core.models.workloads import WorkloadAction, WorkloadRunStatus
from aqp_platform_core.runtime.progress import (
    NullProgressEmitter,
    ProgressEmitter,
)

logger = logging.getLogger(__name__)

_KIND_TO_WORKLOAD_ACTION: dict[TerraformRunKind, WorkloadAction] = {
    TerraformRunKind.PLAN: WorkloadAction.TERRAFORM_PLAN,
    TerraformRunKind.APPLY: WorkloadAction.TERRAFORM_APPLY,
    TerraformRunKind.DESTROY: WorkloadAction.TERRAFORM_DESTROY,
    TerraformRunKind.REFRESH: WorkloadAction.TERRAFORM_REFRESH,
    TerraformRunKind.IMPORT: WorkloadAction.TERRAFORM_IMPORT,
    TerraformRunKind.STATE_PULL: WorkloadAction.TERRAFORM_STATE_PULL,
    TerraformRunKind.VALIDATE: WorkloadAction.TERRAFORM_VALIDATE,
    TerraformRunKind.UNLOCK: WorkloadAction.TERRAFORM_UNLOCK,
}


class TerraformRuntimeError(RuntimeError):
    """Base class for runtime-side failures (not executor failures)."""


@dataclass(slots=True)
class TerraformRequestContext:
    """User + tenancy context propagated into TerraformRun rows.

    Mirrors :class:`aqp_platform_core.runtime.workload.WorkloadRequestContext`
    so the audit sink can stamp ``experiment_id`` + ``test_id`` (rule 34).
    """

    user_id: str
    org_id: str | None = None
    workspace_id: str | None = None
    experiment_id: str | None = None
    test_id: str | None = None
    request_id: str | None = None
    approver_user_id: str | None = None


class TerraformExecutor:
    """The only sanctioned ``subprocess.run(["terraform", ...])`` caller.

    Everyone else (including the runtime above) goes through this
    class so the CI lint can guard against arbitrary shell-outs to
    terraform from the rest of the codebase.

    The executor is deliberately small: it writes the rendered HCL
    bundle to a workspace dir, runs ``terraform init`` once per
    spec hash (cached), then runs the requested command (``plan``,
    ``apply``, etc.) and returns the captured stdout / stderr / rc.
    """

    def __init__(
        self,
        *,
        workspaces_dir: str,
        terraform_binary: str | None = None,
        timeout_seconds: float = 1800.0,
    ) -> None:
        self._workspaces_dir = Path(workspaces_dir)
        self._terraform_binary = terraform_binary or shutil.which("terraform") or "terraform"
        self._timeout_seconds = timeout_seconds

    @property
    def workspaces_dir(self) -> Path:
        return self._workspaces_dir

    @property
    def terraform_binary(self) -> str:
        return self._terraform_binary

    def workspace_path(self, spec: TerraformStackSpec) -> Path:
        return self._workspaces_dir / spec.workspace_id

    def render_workspace(self, spec: TerraformStackSpec) -> Path:
        """Write the spec's HCL bundle to disk + return the workspace path."""
        ws = self.workspace_path(spec)
        ws.mkdir(parents=True, exist_ok=True)
        for rel_path, contents in spec.hcl_modules.items():
            safe_rel = Path(rel_path)
            if safe_rel.is_absolute() or ".." in safe_rel.parts:
                raise TerraformRuntimeError(
                    f"unsafe relative path in hcl_modules: {rel_path!r}"
                )
            dest = ws / safe_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(contents, encoding="utf-8")
        if spec.providers_lock:
            (ws / ".terraform.lock.hcl").write_text(
                spec.providers_lock, encoding="utf-8"
            )
        # Persist variables as a terraform.tfvars.json for the apply step.
        if spec.variables:
            (ws / "terraform.tfvars.json").write_text(
                json.dumps(spec.variables, indent=2, default=str),
                encoding="utf-8",
            )
        return ws

    def run_command(
        self,
        *,
        spec: TerraformStackSpec,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run ``terraform <args...>`` in the spec's workspace dir.

        Returns ``(returncode, stdout, stderr)``. Raises
        :class:`TerraformRuntimeError` only when the executable
        can't be invoked at all (binary missing, permission denied).
        """
        ws = self.workspace_path(spec)
        cmd = [self._terraform_binary, *args]
        run_env = {**os.environ, **(env or {})}
        try:
            result = subprocess.run(  # noqa: S603 - executor IS the sanctioned caller
                cmd,
                cwd=str(ws),
                env=run_env,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TerraformRuntimeError(
                f"terraform binary {self._terraform_binary!r} not found"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            return (
                124,
                exc.stdout or "",
                (exc.stderr or "") + "\n[timeout]",
            )
        return result.returncode, result.stdout, result.stderr


class TerraformRuntime:
    """High-level runtime — orchestrates plan / apply / destroy with audit + progress.

    Construction wiring:

    - ``executor`` — the only sanctioned subprocess caller.
    - ``progress_emitter`` — pluggable AGENTS-rule-4 emitter; defaults
      to :class:`NullProgressEmitter`.
    - ``kill_switch_path`` — optional sentinel file; if present, every
      mutating action returns ``status=rejected`` without invoking
      the executor (the operator can flip the kill-switch by touching
      this file without restarting the CP).

    The runtime stays callable from sync routes; the underlying
    executor I/O is wrapped in ``asyncio.to_thread`` by the async
    method shims.
    """

    def __init__(
        self,
        *,
        executor: TerraformExecutor,
        progress_emitter: ProgressEmitter | None = None,
        kill_switch_path: str | None = None,
        log_excerpt_tail_lines: int = 200,
    ) -> None:
        self._executor = executor
        self._emitter: ProgressEmitter = progress_emitter or NullProgressEmitter()
        self._kill_switch_path = Path(kill_switch_path) if kill_switch_path else None
        self._tail_lines = log_excerpt_tail_lines

    @property
    def executor(self) -> TerraformExecutor:
        return self._executor

    @property
    def emitter(self) -> ProgressEmitter:
        return self._emitter

    def should_halt(self) -> bool:
        if self._kill_switch_path is None:
            return False
        return self._kill_switch_path.exists()

    def halt(self, reason: str = "kill-switch") -> Path:
        """Touch the kill-switch sentinel."""
        if self._kill_switch_path is None:
            raise TerraformRuntimeError("kill-switch path not configured")
        self._kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
        self._kill_switch_path.write_text(reason, encoding="utf-8")
        return self._kill_switch_path

    def clear_halt(self) -> None:
        if self._kill_switch_path is not None and self._kill_switch_path.exists():
            self._kill_switch_path.unlink()

    async def execute(
        self,
        *,
        spec: TerraformStackSpec,
        kind: TerraformRunKind,
        ctx: TerraformRequestContext,
        extra_args: tuple[str, ...] = (),
    ) -> TerraformRunResult:
        """Run one Terraform action end-to-end with audit + progress."""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        spec_hash = spec.compute_hash()
        action_extras = {
            "spec_hash": spec_hash,
            "stack_name": spec.stack_name,
            "workspace_id": spec.workspace_id,
            "state_backend": spec.state_backend.value,
            "kind": kind.value,
            "user_id": ctx.user_id,
        }
        self._emitter.emit(
            run_id,
            "start",
            f"terraform {kind.value} starting",
            context=ctx,
            **action_extras,
        )

        if kind in (TerraformRunKind.APPLY, TerraformRunKind.DESTROY) and self.should_halt():
            self._emitter.emit_error(
                run_id,
                "terraform kill-switch active; mutating action rejected",
                context=ctx,
                **action_extras,
            )
            return TerraformRunResult(
                run_id=run_id,
                run_kind=kind,
                status=TerraformRunStatus.REJECTED,
                stack_name=spec.stack_name,
                workspace_id=spec.workspace_id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_ms=0.0,
                initiated_by_user_id=ctx.user_id,
                approver_user_id=ctx.approver_user_id,
                experiment_id=ctx.experiment_id,
                test_id=ctx.test_id,
                spec_hash=spec_hash,
                halt_reason="kill-switch",
            )

        t0 = time.monotonic()
        rc, stdout, stderr = await asyncio.to_thread(self._execute_sync, spec, kind, extra_args)
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        finished_at = datetime.now(timezone.utc)
        log_excerpt = _tail(stdout + "\n" + stderr, self._tail_lines)
        plan_summary = _parse_plan_summary(stdout) if kind == TerraformRunKind.PLAN else {}

        if rc == 0:
            self._emitter.emit_done(
                run_id,
                {"plan_summary": plan_summary},
                context=ctx,
                **action_extras,
            )
            status = TerraformRunStatus.SUCCEEDED
            error = None
        else:
            self._emitter.emit_error(
                run_id,
                f"terraform {kind.value} returned rc={rc}",
                context=ctx,
                **action_extras,
            )
            status = TerraformRunStatus.FAILED
            error = f"rc={rc}"

        return TerraformRunResult(
            run_id=run_id,
            run_kind=kind,
            status=status,
            stack_name=spec.stack_name,
            workspace_id=spec.workspace_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=elapsed_ms,
            plan_summary=plan_summary,
            log_excerpt=log_excerpt,
            error=error,
            initiated_by_user_id=ctx.user_id,
            approver_user_id=ctx.approver_user_id,
            experiment_id=ctx.experiment_id,
            test_id=ctx.test_id,
            spec_hash=spec_hash,
        )

    def _execute_sync(
        self,
        spec: TerraformStackSpec,
        kind: TerraformRunKind,
        extra_args: tuple[str, ...],
    ) -> tuple[int, str, str]:
        self._executor.render_workspace(spec)
        # init (idempotent; terraform handles repeat invocations cheaply).
        init_rc, init_stdout, init_stderr = self._executor.run_command(
            spec=spec, args=["init", "-input=false", "-no-color"]
        )
        if init_rc != 0:
            return init_rc, init_stdout, init_stderr
        args = _build_args_for_kind(kind, extra_args)
        return self._executor.run_command(spec=spec, args=args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_args_for_kind(
    kind: TerraformRunKind, extra_args: tuple[str, ...]
) -> list[str]:
    base: list[str] = []
    if kind == TerraformRunKind.PLAN:
        base = ["plan", "-input=false", "-no-color", "-out=tfplan"]
    elif kind == TerraformRunKind.APPLY:
        base = ["apply", "-input=false", "-no-color", "-auto-approve"]
    elif kind == TerraformRunKind.DESTROY:
        base = ["destroy", "-input=false", "-no-color", "-auto-approve"]
    elif kind == TerraformRunKind.REFRESH:
        base = ["refresh", "-input=false", "-no-color"]
    elif kind == TerraformRunKind.VALIDATE:
        base = ["validate", "-no-color"]
    elif kind == TerraformRunKind.STATE_PULL:
        base = ["state", "pull"]
    elif kind == TerraformRunKind.IMPORT:
        base = ["import", "-input=false", "-no-color"]
    elif kind == TerraformRunKind.UNLOCK:
        base = ["force-unlock", "-force"]
    base.extend(extra_args)
    return base


def _tail(text: str, lines: int) -> str:
    if not text or lines <= 0:
        return ""
    parts = text.splitlines()
    if len(parts) <= lines:
        return text
    return "\n".join(parts[-lines:])


def _parse_plan_summary(stdout: str) -> dict[str, Any]:
    """Best-effort scrape of the ``Plan: X to add, Y to change, Z to destroy.`` line."""
    summary: dict[str, Any] = {"raw": ""}
    for line in stdout.splitlines():
        if line.startswith("Plan:"):
            summary["raw"] = line.strip()
            try:
                # Plan: 3 to add, 1 to change, 0 to destroy.
                parts = (
                    line.replace("Plan:", "")
                    .replace(".", "")
                    .strip()
                    .split(",")
                )
                for part in parts:
                    tokens = part.strip().split()
                    if len(tokens) >= 3 and tokens[2] in {"add", "change", "destroy"}:
                        summary[tokens[2]] = int(tokens[0])
            except Exception:  # noqa: BLE001
                logger.debug("plan summary parse failed", exc_info=True)
            return summary
    return summary


def workload_action_for(kind: TerraformRunKind) -> WorkloadAction:
    """Return the matching :class:`WorkloadAction` for an audit row."""
    return _KIND_TO_WORKLOAD_ACTION[kind]


def run_status_to_workload_status(
    status: TerraformRunStatus,
) -> WorkloadRunStatus:
    """Project a :class:`TerraformRunStatus` onto the workload ledger shape."""
    mapping = {
        TerraformRunStatus.PENDING: WorkloadRunStatus.PENDING,
        TerraformRunStatus.RUNNING: WorkloadRunStatus.RUNNING,
        TerraformRunStatus.SUCCEEDED: WorkloadRunStatus.SUCCEEDED,
        TerraformRunStatus.FAILED: WorkloadRunStatus.FAILED,
        TerraformRunStatus.HALTED: WorkloadRunStatus.HALTED,
        TerraformRunStatus.REJECTED: WorkloadRunStatus.REJECTED,
    }
    return mapping[status]


__all__ = [
    "TerraformExecutor",
    "TerraformRequestContext",
    "TerraformRuntime",
    "TerraformRuntimeError",
    "run_status_to_workload_status",
    "workload_action_for",
]
