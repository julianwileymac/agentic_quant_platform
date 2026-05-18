"""``TerraformRuntime`` — single sanctioned executor for Terraform IaC lifecycles.

AGENTS rule 42 — every Terraform plan / apply / destroy / refresh /
state-pull / import goes through this runtime. Nothing else in the
codebase calls :class:`TerraformExecutor` or :class:`HcpClient`
directly.

Mirrors :class:`aqp.bots.runtime.BotRuntime`:

1. Snapshot + persist the spec version (hash-locked ->
   ``terraform_stack_spec_versions``, rule 43).
2. Open a :class:`TerraformRun` ledger row, stamp the
   :class:`RequestContext` (rule 34 -> ``experiment_id`` + ``test_id``).
3. Drive the underlying executor (local subprocess OR HCP HTTP).
4. Emit progress through :mod:`aqp.tasks._progress` so existing
   ``/chat/stream/<task_id>`` WebSocket consumers light up unchanged.
5. Finalise the run row with status + plan summary + log URIs.

Tenancy + safety hooks:

- :meth:`should_halt` checks the kill-switch Redis key before each
  state-mutating operation and refuses to start when set.
- Apply / destroy require ``approver_user_id`` to be different from
  the ``started_by_user_id`` when the workspace's
  ``hard_mandatory`` policy attachment is non-empty (four-eyes
  approval).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.terraform.spec import TerraformStackSpec

logger = logging.getLogger(__name__)


TerraformRunKind = Literal[
    "plan", "apply", "destroy", "refresh", "import", "state_pull", "validate", "unlock"
]


@dataclass
class TerraformRunResult:
    """Outcome of one :class:`TerraformRuntime` action."""

    run_id: str
    spec_version_id: str | None
    workspace_id: str
    run_kind: str
    status: str
    started_at: float
    duration_ms: float = 0.0
    task_id: str | None = None
    exit_code: int | None = None
    plan_summary: dict[str, Any] = field(default_factory=dict)
    plan_artifact_uri: str | None = None
    stdout_log_uri: str | None = None
    stderr_log_uri: str | None = None
    policy_check: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TerraformHaltedError(RuntimeError):
    """Raised when the kill switch / halt label blocks a run."""


class TerraformPolicyDeniedError(RuntimeError):
    """Raised when an OPA hard-mandatory policy check fails for an apply."""


class TerraformApprovalRequiredError(PermissionError):
    """Raised when an apply / destroy lacks the required approver."""


class TerraformRuntime:
    """Executor for a single :class:`TerraformStackSpec`.

    Construct one runtime per (spec, workspace) tuple. The runtime is
    cheap to build (no I/O until a method is called) so callers
    typically instantiate fresh per request.
    """

    def __init__(
        self,
        spec: TerraformStackSpec,
        *,
        workspace_id: str,
        task_id: str | None = None,
        run_id: str | None = None,
        context: Any | None = None,
        prerendered_workspace_dir: str | None = None,
    ) -> None:
        self.spec = spec
        self.workspace_id = workspace_id
        self.task_id = task_id
        self.run_id = run_id or str(uuid.uuid4())
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:
                context = None
        self.context = context
        self._spec_version_id: str | None = None
        self._executor: Any | None = None
        self._workspace_row_id: str | None = None
        self._workspace_slug: str | None = None
        self._workspace_org_id: str | None = None
        # When set, the executor skips ``render_spec`` codegen and
        # operates on the supplied directory directly. The local AQP
        # stack uses this to point at terraform/environments/local/.
        self._prerendered_workspace_dir = prerendered_workspace_dir

    # ------------------------------------------------------------------
    # Spec persistence + workspace lookup
    # ------------------------------------------------------------------

    def _persist_spec(self) -> str | None:
        if self._spec_version_id is not None:
            return self._spec_version_id
        from aqp.terraform.codegen import render_spec
        from aqp.terraform.registry import persist_spec

        try:
            rendered = render_spec(self.spec)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "TerraformRuntime: codegen failed for spec %s: %s",
                self.spec.name,
                exc,
            )
            rendered = None
        self._spec_version_id = persist_spec(
            self.spec,
            project_id=getattr(self.context, "project_id", None),
            payload_hcl=rendered,
        )
        return self._spec_version_id

    def _resolve_workspace_slug(self) -> str:
        if self._workspace_slug is not None:
            return self._workspace_slug
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import TerraformWorkspace

            workspace_row_id = self._resolve_workspace_row_id()
            with SessionLocal() as session:
                row = (
                    session.query(TerraformWorkspace)
                    .filter(TerraformWorkspace.id == workspace_row_id)
                    .one_or_none()
                )
                if row is not None:
                    self._workspace_row_id = row.id
                    self._workspace_slug = row.slug
                    self._workspace_org_id = row.tenant_org_id
                    return row.slug
        except Exception:  # noqa: BLE001
            logger.debug(
                "TerraformRuntime: workspace lookup failed for id=%s",
                self.workspace_id,
                exc_info=True,
            )
        # Fall back to the spec slug so the executor still has a directory name.
        self._workspace_slug = self.spec.slug
        return self.spec.slug

    def _resolve_workspace_row_id(self, *, spec_version_id: str | None = None) -> str:
        """Resolve the canonical ``terraform_workspaces.id`` for this runtime.

        Standard API-driven runs pass an existing workspace UUID and this method
        simply returns it. Prerendered stacks (local/rpi convenience paths) can
        start before any workspace row exists; in that case we upsert a synthetic
        workspace row so ``TerraformRun`` FK writes succeed.
        """
        if self._workspace_row_id is not None:
            return self._workspace_row_id
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import (
                TerraformStackSpecVersion,
                TerraformWorkspace,
            )
        except Exception:  # pragma: no cover
            self._workspace_row_id = self.workspace_id
            return self.workspace_id

        try:
            with SessionLocal() as session:
                # First try the id exactly as supplied.
                row = (
                    session.query(TerraformWorkspace)
                    .filter(TerraformWorkspace.id == self.workspace_id)
                    .one_or_none()
                )
                # Prerendered stacks often supply ``workspace_id=spec.slug``;
                # if no row by id exists, match by slug before creating.
                if row is None and self._prerendered_workspace_dir:
                    row = (
                        session.query(TerraformWorkspace)
                        .filter(TerraformWorkspace.slug == self.spec.slug)
                        .order_by(TerraformWorkspace.created_at.desc())
                        .first()
                    )
                if row is None and self._prerendered_workspace_dir:
                    workspace_id = str(self.workspace_id or "").strip()
                    if not workspace_id or len(workspace_id) > 36:
                        workspace_id = str(uuid.uuid4())
                    row = TerraformWorkspace(
                        id=workspace_id,
                        slug=self.spec.slug,
                        name=self.spec.name,
                        environment=self.spec.environment,
                        state_backend=self.spec.backend.kind,
                        owner_user_id=getattr(self.context, "user_id", None),
                        workspace_id=getattr(self.context, "workspace_id", None),
                        project_id=getattr(self.context, "project_id", None),
                        tenant_org_id=getattr(self.context, "org_id", None),
                    )
                    if spec_version_id:
                        version = (
                            session.query(TerraformStackSpecVersion)
                            .filter(TerraformStackSpecVersion.id == spec_version_id)
                            .one_or_none()
                        )
                        if version is not None:
                            row.stack_spec_id = version.spec_id
                    session.add(row)
                    session.commit()
                    session.refresh(row)

                if row is not None:
                    if spec_version_id and not row.stack_spec_id:
                        version = (
                            session.query(TerraformStackSpecVersion)
                            .filter(TerraformStackSpecVersion.id == spec_version_id)
                            .one_or_none()
                        )
                        if version is not None:
                            row.stack_spec_id = version.spec_id
                            session.add(row)
                            session.commit()
                    self._workspace_row_id = row.id
                    self._workspace_slug = row.slug
                    self._workspace_org_id = row.tenant_org_id
                    return row.id
        except Exception:  # noqa: BLE001
            logger.debug(
                "TerraformRuntime: workspace id resolution failed for id=%s",
                self.workspace_id,
                exc_info=True,
            )

        self._workspace_row_id = self.workspace_id
        return self.workspace_id

    def _get_executor(self):
        if self._executor is not None:
            return self._executor
        from aqp.terraform.runner import TerraformExecutor

        kwargs: dict[str, Any] = {
            "workspace_slug": self._resolve_workspace_slug(),
            "spec": self.spec,
        }
        if self._prerendered_workspace_dir:
            kwargs["prerendered_workspace_dir"] = self._prerendered_workspace_dir
        topology_env = self._topology_env_overrides()
        if topology_env:
            kwargs["env_overrides"] = topology_env
        self._executor = TerraformExecutor(**kwargs)
        return self._executor

    def _topology_env_overrides(self) -> dict[str, str]:
        """Best-effort target-specific Terraform env from deployment topology."""
        try:
            from aqp.deployment.topology import get_deployment_topology

            topology = get_deployment_topology()
            target = topology.target_by_stack_slug(self.spec.slug)
            if target is None:
                target = topology.target_by_stack_slug(self.workspace_id)
            if target is None:
                return {}
            return topology.terraform_env_overrides(target.id)
        except Exception:  # noqa: BLE001
            logger.debug(
                "TerraformRuntime: topology env lookup failed for spec=%s workspace=%s",
                self.spec.slug,
                self.workspace_id,
                exc_info=True,
            )
            return {}

    # ------------------------------------------------------------------
    # Kill switch + approval gate
    # ------------------------------------------------------------------

    def should_halt(self) -> bool:
        """Return True iff the AQP kill switch is set for terraform runs.

        Returns ``False`` on any Redis failure — the kill switch is
        an availability-blocker, not an availability-killer.
        """
        try:
            import redis

            from aqp.config import settings

            kill_key = str(getattr(settings, "risk_kill_switch_key", "aqp:kill_switch"))
            client = redis.Redis.from_url(str(settings.redis_url))
            return bool(client.get(kill_key))
        except Exception:  # noqa: BLE001
            return False

    def _check_halt(self) -> None:
        if self.should_halt():
            raise TerraformHaltedError(
                f"Kill switch is set; refusing to run terraform action on workspace {self.workspace_id}"
            )

    def _require_approval(
        self,
        *,
        run_kind: str,
        started_by_user_id: str | None,
        approver_user_id: str | None,
    ) -> None:
        """Four-eyes enforcement for state-mutating actions.

        When a workspace has at least one ``hard_mandatory=True``
        :class:`TerraformPolicyAttachment`, an apply / destroy / unlock
        requires ``approver_user_id != started_by_user_id``. Otherwise
        any ``approver_user_id`` (including the same user) is accepted
        so the local-dev loop stays frictionless.
        """
        if run_kind not in {"apply", "destroy", "unlock"}:
            return
        workspace_row_id = self._resolve_workspace_row_id()
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import TerraformPolicyAttachment

            with SessionLocal() as session:
                row = (
                    session.query(TerraformPolicyAttachment)
                    .filter(
                        TerraformPolicyAttachment.terraform_workspace_id
                        == workspace_row_id
                    )
                    .filter(TerraformPolicyAttachment.hard_mandatory.is_(True))
                    .first()
                )
                if row is None:
                    return
        except Exception:  # noqa: BLE001
            return
        if not approver_user_id:
            raise TerraformApprovalRequiredError(
                f"workspace {self.workspace_id} has a hard-mandatory policy "
                "attachment; approver_user_id is required"
            )
        if started_by_user_id and approver_user_id == started_by_user_id:
            raise TerraformApprovalRequiredError(
                "four-eyes policy violation: approver must differ from initiator"
            )

    # ------------------------------------------------------------------
    # Ledger row management
    # ------------------------------------------------------------------

    def _open_run_row(
        self,
        *,
        run_kind: TerraformRunKind,
        started_by_user_id: str | None,
        approver_user_id: str | None = None,
        celery_task_id: str | None = None,
    ) -> str | None:
        spec_version_id = self._persist_spec()
        workspace_row_id = self._resolve_workspace_row_id(spec_version_id=spec_version_id)
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import TerraformRun

            with SessionLocal() as session:
                row = TerraformRun(
                    id=self.run_id,
                    terraform_workspace_id=workspace_row_id,
                    spec_version_id=spec_version_id,
                    run_kind=run_kind,
                    status="running",
                    started_by_user_id=started_by_user_id
                    or getattr(self.context, "user_id", None),
                    approved_by_user_id=approver_user_id,
                    celery_task_id=celery_task_id,
                )
                # Tenancy stamp via direct attribute set (LedgerWriter is
                # shaped for ``LedgerEntry`` rows; this is a custom one).
                row.owner_user_id = getattr(self.context, "user_id", None)
                row.workspace_id = getattr(self.context, "workspace_id", None)
                row.project_id = getattr(self.context, "project_id", None)
                row.experiment_id = getattr(self.context, "experiment_id", None)
                row.test_id = getattr(self.context, "test_id", None)
                session.add(row)
                session.commit()
                return row.id
        except Exception:  # noqa: BLE001
            logger.exception(
                "Could not open TerraformRun ledger row for workspace=%s kind=%s",
                self.workspace_id,
                run_kind,
            )
            return None

    def _finalize_run_row(
        self,
        *,
        run_id: str | None,
        status: str,
        executor_result: Any | None = None,
        policy_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if run_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import TerraformRun

            with SessionLocal() as session:
                row = (
                    session.query(TerraformRun)
                    .filter(TerraformRun.id == run_id)
                    .one_or_none()
                )
                if row is None:
                    return
                row.status = status
                row.finished_at = datetime.utcnow()
                if executor_result is not None:
                    payload = executor_result.to_run_row_payload()
                    for key, value in payload.items():
                        if value is not None:
                            setattr(row, key, value)
                if policy_payload is not None:
                    row.policy_check_result = policy_payload
                if error is not None:
                    row.error = error
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Could not finalise TerraformRun row=%s status=%s",
                run_id,
                status,
            )

    # ------------------------------------------------------------------
    # Public lifecycle methods
    # ------------------------------------------------------------------

    def plan(
        self,
        *,
        started_by_user_id: str | None = None,
        var_overrides: dict[str, str] | None = None,
        destroy: bool = False,
    ) -> TerraformRunResult:
        """Run ``terraform plan`` and persist a :class:`TerraformRun` row."""
        return self._with_run(
            run_kind="plan",
            stage_message=f"Planning terraform stack {self.spec.name!r}",
            action=lambda: self._get_executor().plan(
                destroy=destroy, var_overrides=var_overrides
            ),
            started_by_user_id=started_by_user_id,
        )

    def outputs(self) -> dict[str, Any]:
        """Read ``terraform output -json`` through the sanctioned executor."""
        try:
            return self._get_executor().outputs_json()
        except Exception:  # noqa: BLE001
            logger.debug(
                "TerraformRuntime: output read failed for workspace=%s",
                self.workspace_id,
                exc_info=True,
            )
            return {}

    def apply(
        self,
        *,
        started_by_user_id: str | None = None,
        approver_user_id: str | None = None,
        plan_file: str | None = "tfplan",
    ) -> TerraformRunResult:
        """Run ``terraform apply`` against the previously generated plan."""
        self._check_halt()
        self._require_approval(
            run_kind="apply",
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )
        return self._with_run(
            run_kind="apply",
            stage_message=f"Applying terraform stack {self.spec.name!r}",
            action=lambda: self._get_executor().apply(plan_file=plan_file),
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )

    def destroy(
        self,
        *,
        started_by_user_id: str | None = None,
        approver_user_id: str | None = None,
    ) -> TerraformRunResult:
        """Run ``terraform destroy``."""
        self._check_halt()
        self._require_approval(
            run_kind="destroy",
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )
        return self._with_run(
            run_kind="destroy",
            stage_message=f"Destroying terraform stack {self.spec.name!r}",
            action=lambda: self._get_executor().destroy(),
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )

    def refresh(
        self,
        *,
        started_by_user_id: str | None = None,
    ) -> TerraformRunResult:
        """Run ``terraform apply -refresh-only`` to sync the state file."""
        return self._with_run(
            run_kind="refresh",
            stage_message=f"Refreshing state for stack {self.spec.name!r}",
            action=lambda: self._get_executor().refresh(),
            started_by_user_id=started_by_user_id,
        )

    def state_pull(
        self,
        *,
        started_by_user_id: str | None = None,
    ) -> TerraformRunResult:
        """Run ``terraform state pull`` and persist the result."""
        return self._with_run(
            run_kind="state_pull",
            stage_message=f"Pulling state for stack {self.spec.name!r}",
            action=lambda: self._get_executor().state_pull(),
            started_by_user_id=started_by_user_id,
        )

    def validate(
        self,
        *,
        started_by_user_id: str | None = None,
    ) -> TerraformRunResult:
        return self._with_run(
            run_kind="validate",
            stage_message=f"Validating stack {self.spec.name!r}",
            action=lambda: self._get_executor().validate(),
            started_by_user_id=started_by_user_id,
        )

    def unlock(
        self,
        lock_id: str,
        *,
        started_by_user_id: str | None = None,
        approver_user_id: str | None = None,
    ) -> TerraformRunResult:
        self._require_approval(
            run_kind="unlock",
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )
        return self._with_run(
            run_kind="unlock",
            stage_message=f"Force-unlocking stack {self.spec.name!r} (lock={lock_id})",
            action=lambda: self._get_executor().unlock(lock_id),
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _with_run(
        self,
        *,
        run_kind: TerraformRunKind,
        stage_message: str,
        action,
        started_by_user_id: str | None = None,
        approver_user_id: str | None = None,
    ) -> TerraformRunResult:
        task_id = self.task_id or self.run_id
        started = time.time()
        run_id = self._open_run_row(
            run_kind=run_kind,
            started_by_user_id=started_by_user_id,
            approver_user_id=approver_user_id,
            celery_task_id=task_id,
        )
        emit(task_id, "start", stage_message, run_kind=run_kind, run_id=run_id)
        try:
            executor_result = action()
        except TerraformHaltedError as exc:
            self._finalize_run_row(run_id=run_id, status="cancelled", error=str(exc))
            emit_error(task_id, str(exc))
            return TerraformRunResult(
                run_id=run_id or self.run_id,
                spec_version_id=self._spec_version_id,
                workspace_id=self.workspace_id,
                run_kind=run_kind,
                status="cancelled",
                started_at=started,
                duration_ms=(time.time() - started) * 1000.0,
                task_id=task_id,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("terraform %s failed", run_kind)
            self._finalize_run_row(run_id=run_id, status="errored", error=str(exc))
            emit_error(task_id, f"terraform {run_kind} failed: {exc}")
            return TerraformRunResult(
                run_id=run_id or self.run_id,
                spec_version_id=self._spec_version_id,
                workspace_id=self.workspace_id,
                run_kind=run_kind,
                status="errored",
                started_at=started,
                duration_ms=(time.time() - started) * 1000.0,
                task_id=task_id,
                error=str(exc),
            )

        # Policy check (apply only).
        policy_payload: dict[str, Any] = {}
        if run_kind == "apply" and executor_result.plan_summary_path:
            policy_payload = self._evaluate_policy(executor_result.plan_summary_path)
            if policy_payload.get("passed") is False and not policy_payload.get("skipped"):
                self._finalize_run_row(
                    run_id=run_id,
                    status="policy_failed",
                    executor_result=executor_result,
                    policy_payload=policy_payload,
                    error="OPA policy denied the plan",
                )
                emit_error(task_id, "OPA policy denied the plan")
                return TerraformRunResult(
                    run_id=run_id or self.run_id,
                    spec_version_id=self._spec_version_id,
                    workspace_id=self.workspace_id,
                    run_kind=run_kind,
                    status="policy_failed",
                    started_at=started,
                    duration_ms=executor_result.duration_ms,
                    task_id=task_id,
                    exit_code=executor_result.exit_code,
                    plan_summary=executor_result.plan_summary,
                    plan_artifact_uri=(
                        f"file://{executor_result.plan_artifact_path}"
                        if executor_result.plan_artifact_path
                        else None
                    ),
                    stdout_log_uri=f"file://{executor_result.stdout_log_path}",
                    stderr_log_uri=f"file://{executor_result.stderr_log_path}",
                    policy_check=policy_payload,
                    error="OPA policy denied the plan",
                )

        # Snapshot state version row on successful apply.
        if run_kind == "apply" and executor_result.exit_code == 0:
            self._snapshot_state_version(run_id=run_id)

        status = (
            "completed"
            if executor_result.exit_code in (0, 2)  # 2 = plan changes detected
            else "errored"
        )
        self._finalize_run_row(
            run_id=run_id,
            status=status,
            executor_result=executor_result,
            policy_payload=policy_payload or None,
            error=executor_result.error,
        )
        if status == "errored":
            emit_error(task_id, executor_result.error or f"terraform {run_kind} failed")
        else:
            emit_done(
                task_id,
                {
                    "run_id": run_id,
                    "exit_code": executor_result.exit_code,
                    "plan_summary": executor_result.plan_summary,
                },
            )
        return TerraformRunResult(
            run_id=run_id or self.run_id,
            spec_version_id=self._spec_version_id,
            workspace_id=self.workspace_id,
            run_kind=run_kind,
            status=status,
            started_at=started,
            duration_ms=executor_result.duration_ms,
            task_id=task_id,
            exit_code=executor_result.exit_code,
            plan_summary=executor_result.plan_summary,
            plan_artifact_uri=(
                f"file://{executor_result.plan_artifact_path}"
                if executor_result.plan_artifact_path
                else None
            ),
            stdout_log_uri=f"file://{executor_result.stdout_log_path}",
            stderr_log_uri=f"file://{executor_result.stderr_log_path}",
            policy_check=policy_payload,
            error=executor_result.error,
        )

    def _evaluate_policy(self, plan_json_path: str) -> dict[str, Any]:
        workspace_row_id = self._resolve_workspace_row_id()
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import TerraformPolicyAttachment
            from aqp.terraform.policy import check_plan_against_opa

            with SessionLocal() as session:
                row = (
                    session.query(TerraformPolicyAttachment)
                    .filter(
                        TerraformPolicyAttachment.terraform_workspace_id == workspace_row_id
                    )
                    .filter(TerraformPolicyAttachment.policy_engine == "opa")
                    .first()
                )
                if row is None:
                    return {"passed": True, "skipped": True, "reason": "no policy"}
                policy_path = row.policy_set_uri
        except Exception:  # noqa: BLE001
            return {"passed": True, "skipped": True, "reason": "policy lookup failed"}

        result = check_plan_against_opa(
            plan_json_path=plan_json_path,
            policy_path=policy_path,
        )
        return result.to_json()

    def _snapshot_state_version(self, *, run_id: str | None) -> None:
        """Create a :class:`TerraformStateVersion` row after a successful apply."""
        workspace_row_id = self._resolve_workspace_row_id()
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_terraform import (
                TerraformStateVersion,
            )

            with SessionLocal() as session:
                last = (
                    session.query(TerraformStateVersion)
                    .filter(
                        TerraformStateVersion.terraform_workspace_id == workspace_row_id
                    )
                    .order_by(TerraformStateVersion.serial.desc())
                    .first()
                )
                next_serial = (last.serial + 1) if last else 1
                row = TerraformStateVersion(
                    id=str(uuid.uuid4()),
                    terraform_workspace_id=workspace_row_id,
                    serial=next_serial,
                    lineage=None,
                    state_json_uri=f"workspace://{workspace_row_id}/state/{next_serial}",
                    outputs_redacted={},
                    created_by_run_id=run_id,
                )
                row.owner_user_id = getattr(self.context, "user_id", None)
                row.workspace_id = getattr(self.context, "workspace_id", None)
                row.project_id = getattr(self.context, "project_id", None)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not snapshot TerraformStateVersion for workspace=%s",
                self.workspace_id,
                exc_info=True,
            )


__all__ = [
    "TerraformApprovalRequiredError",
    "TerraformHaltedError",
    "TerraformPolicyDeniedError",
    "TerraformRunKind",
    "TerraformRunResult",
    "TerraformRuntime",
]
