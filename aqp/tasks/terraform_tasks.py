"""Celery tasks driving :class:`aqp.terraform.runtime.TerraformRuntime`.

Thin wrappers per AGENTS-rule 42: routes/MCP tools enqueue these
tasks; the task body re-fetches the spec + workspace from Postgres
and dispatches through :class:`TerraformRuntime`. Each task emits
canonical progress frames via :mod:`aqp.tasks._progress`.

Queues:

- ``terraform`` (declared in
  :data:`aqp.tasks.celery_app.celery_app.conf.task_routes`).

Beat:

- ``aqp.tasks.terraform_tasks.terraform_drift_scan`` runs hourly
  (period = ``settings.terraform_drift_scan_period_seconds``) and
  enqueues a ``refresh`` run for every non-archived workspace so
  drift is caught before the next operator-driven plan.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app
from aqp.tasks.secure_task import SecureTask

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (lazy ORM imports per AGENTS rule "no Celery deps at module top of
# route files" — the same hygiene applies here so Celery worker boot stays
# fast).
# ---------------------------------------------------------------------------


def _load_run_and_spec(run_id: str):
    """Pull a :class:`TerraformRun` row + reconstruct the matching spec."""
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_terraform import (
        TerraformRun,
        TerraformStackSpecVersion,
        TerraformWorkspace,
    )
    from aqp.terraform.spec import TerraformStackSpec

    with SessionLocal() as session:
        run = (
            session.query(TerraformRun)
            .filter(TerraformRun.id == run_id)
            .one_or_none()
        )
        if run is None:
            raise ValueError(f"TerraformRun {run_id!r} not found")
        ws = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == run.terraform_workspace_id)
            .one_or_none()
        )
        if ws is None:
            raise ValueError(
                f"TerraformWorkspace {run.terraform_workspace_id!r} not found"
            )
        version = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.id == run.spec_version_id)
            .one_or_none()
            if run.spec_version_id
            else None
        )
        if version is None:
            raise ValueError(
                f"TerraformStackSpecVersion {run.spec_version_id!r} not found"
            )
        spec = TerraformStackSpec.model_validate(version.payload_json)
        return run, ws, spec


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_terraform_plan")
def run_terraform_plan(self, *, run_id: str) -> dict[str, Any]:
    """Execute ``terraform plan`` for an existing :class:`TerraformRun` row."""
    task_id = self.request.id or run_id
    emit(task_id, "load", f"loading run {run_id}", run_id=run_id)
    try:
        run, workspace, spec = _load_run_and_spec(run_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"load failed: {exc}")
        raise
    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=workspace.id,
        task_id=task_id,
        run_id=run.id,
    )
    result = runtime.plan(started_by_user_id=run.started_by_user_id)
    payload = result.to_dict()
    return payload


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_terraform_apply")
def run_terraform_apply(
    self,
    *,
    run_id: str,
    approver_user_id: str | None = None,
    plan_file: str | None = "tfplan",
) -> dict[str, Any]:
    """Execute ``terraform apply`` (gated behind approval + policy)."""
    task_id = self.request.id or run_id
    emit(task_id, "load", f"loading run {run_id}", run_id=run_id)
    try:
        run, workspace, spec = _load_run_and_spec(run_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"load failed: {exc}")
        raise
    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=workspace.id,
        task_id=task_id,
        run_id=run.id,
    )
    result = runtime.apply(
        started_by_user_id=run.started_by_user_id,
        approver_user_id=approver_user_id or run.approved_by_user_id,
        plan_file=plan_file,
    )
    return result.to_dict()


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_terraform_destroy")
def run_terraform_destroy(
    self,
    *,
    run_id: str,
    approver_user_id: str | None = None,
) -> dict[str, Any]:
    """Execute ``terraform destroy`` (gated behind approval)."""
    task_id = self.request.id or run_id
    emit(task_id, "load", f"loading run {run_id}", run_id=run_id)
    try:
        run, workspace, spec = _load_run_and_spec(run_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"load failed: {exc}")
        raise
    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=workspace.id,
        task_id=task_id,
        run_id=run.id,
    )
    result = runtime.destroy(
        started_by_user_id=run.started_by_user_id,
        approver_user_id=approver_user_id or run.approved_by_user_id,
    )
    return result.to_dict()


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_terraform_refresh")
def run_terraform_refresh(self, *, run_id: str) -> dict[str, Any]:
    """Execute ``terraform apply -refresh-only`` to detect drift."""
    task_id = self.request.id or run_id
    try:
        run, workspace, spec = _load_run_and_spec(run_id)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"load failed: {exc}")
        raise
    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=workspace.id,
        task_id=task_id,
        run_id=run.id,
    )
    return runtime.refresh(started_by_user_id=run.started_by_user_id).to_dict()


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.terraform_drift_scan")
def terraform_drift_scan(self) -> dict[str, Any]:
    """Beat task — fan out ``refresh`` runs across every active workspace.

    Idempotent and best-effort: ledger rows are opened lazily by the
    individual ``run_terraform_refresh`` tasks. Workspaces flagged
    ``archived=True`` are skipped.
    """
    task_id = self.request.id or "terraform-drift-scan"
    enqueued = 0
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_terraform import (
            TerraformRun,
            TerraformStackSpecVersion,
            TerraformWorkspace,
        )

        with SessionLocal() as session:
            workspaces = (
                session.query(TerraformWorkspace)
                .filter(TerraformWorkspace.archived.is_(False))
                .all()
            )
            for ws in workspaces:
                latest_version = (
                    session.query(TerraformStackSpecVersion)
                    .filter(TerraformStackSpecVersion.spec_id == ws.stack_spec_id)
                    .order_by(TerraformStackSpecVersion.version.desc())
                    .first()
                    if ws.stack_spec_id
                    else None
                )
                if latest_version is None:
                    continue
                row = TerraformRun(
                    terraform_workspace_id=ws.id,
                    spec_version_id=latest_version.id,
                    run_kind="refresh",
                    status="queued",
                )
                session.add(row)
                session.flush()
                run_id = row.id
                session.commit()
                async_result = run_terraform_refresh.apply_async(
                    kwargs={"run_id": run_id}
                )
                # Stash the celery_task_id on the row.
                row.celery_task_id = async_result.id
                session.merge(row)
                session.commit()
                enqueued += 1
        emit_done(
            task_id,
            {"enqueued": enqueued, "summary": f"drift scan enqueued {enqueued} runs"},
        )
        return {"enqueued": enqueued}
    except Exception as exc:  # noqa: BLE001
        logger.exception("terraform_drift_scan failed")
        emit_error(task_id, str(exc))
        return {"enqueued": enqueued, "error": str(exc)}


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.cancel_terraform_run")
def cancel_terraform_run(self, *, run_id: str) -> dict[str, Any]:
    """Mark a running terraform run as cancelled and best-effort revoke."""
    task_id = self.request.id or run_id
    try:
        from datetime import datetime

        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_terraform import TerraformRun

        with SessionLocal() as session:
            row = (
                session.query(TerraformRun)
                .filter(TerraformRun.id == run_id)
                .one_or_none()
            )
            if row is None:
                emit_error(task_id, f"run {run_id} not found")
                return {"ok": False, "error": "not found"}
            row.status = "cancelled"
            row.halted = True
            row.finished_at = datetime.utcnow()
            if row.celery_task_id:
                try:
                    celery_app.control.revoke(row.celery_task_id, terminate=True)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "revoke failed for celery_task_id=%s",
                        row.celery_task_id,
                        exc_info=True,
                    )
            session.commit()
        emit_done(task_id, {"run_id": run_id, "status": "cancelled"})
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.exception("cancel_terraform_run failed")
        emit_error(task_id, str(exc))
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Local-stack convenience task — drives the canonical topology-defined spec
# against the hand-authored composition under
# terraform/environments/local/. The CLI / REST sugar routes call this
# instead of run_terraform_plan/apply/destroy because:
#   1. The local stack predates a TerraformWorkspace row (the Postgres
#      that owns workspaces is the very thing being booted).
#   2. The codegen path is bypassed via ``prerendered_workspace_dir``
#      so the rich multi-module composition runs as authored.
# Each task lands canonical progress frames and (when Postgres is up)
# a TerraformRun ledger row through TerraformRuntime.
# ---------------------------------------------------------------------------


_LOCAL_TARGET_ID = "local"
_RPI_TARGET_ID = "rpi"
_LOCAL_ACTIONS = {"up", "apply", "down", "destroy", "plan", "refresh", "build"}


def _deployment_target(target_id: str):
    from aqp.deployment.topology import get_target

    return get_target(target_id)


def _resolve_local_env_path() -> str:
    return str(_deployment_target(_LOCAL_TARGET_ID).terraform.environment_path)


def _resolve_rpi_env_path() -> str:
    return str(_deployment_target(_RPI_TARGET_ID).terraform.environment_path)


def _load_local_spec():
    """Hydrate the canonical local TerraformStackSpec.

    Mirrors :func:`aqp.cli.deploy_cmd._load_local_spec` so the CLI and
    the Celery worker resolve the same registry entry.
    """
    from aqp.terraform.registry import (
        add_spec,
        get_terraform_spec,
        reload_yaml_dir,
    )
    from aqp.terraform.spec import (
        TerraformBackendRef,
        TerraformProviderRef,
        TerraformStackSpec,
    )

    target = _deployment_target(_LOCAL_TARGET_ID)
    try:
        return get_terraform_spec(target.terraform.stack_slug)
    except KeyError:
        pass

    from pathlib import Path

    yaml_dir = Path(__file__).resolve().parent.parent.parent / "configs" / "terraform"
    if yaml_dir.exists():
        reload_yaml_dir(yaml_dir)
        try:
            return get_terraform_spec(target.terraform.stack_slug)
        except KeyError:
            pass

    spec = TerraformStackSpec(
        name=target.terraform.stack_slug,
        slug=target.terraform.stack_slug,
        module_kind="composite",
        description="Local AQP stack (synthesised)",
        cloud_provider=target.cloud_provider,
        environment=target.environment,
        provider=TerraformProviderRef(kind=target.cloud_provider),
        backend=TerraformBackendRef(kind="local"),
    )
    add_spec(spec)
    return spec


def _load_rpi_spec():
    from aqp.terraform.registry import add_spec, get_terraform_spec, reload_yaml_dir
    from aqp.terraform.spec import TerraformBackendRef, TerraformProviderRef, TerraformStackSpec

    target = _deployment_target(_RPI_TARGET_ID)
    try:
        return get_terraform_spec(target.terraform.stack_slug)
    except KeyError:
        pass
    from pathlib import Path

    yaml_dir = Path(__file__).resolve().parent.parent.parent / "configs" / "terraform"
    if yaml_dir.exists():
        reload_yaml_dir(yaml_dir)
        try:
            return get_terraform_spec(target.terraform.stack_slug)
        except KeyError:
            pass
    spec = TerraformStackSpec(
        name=target.terraform.stack_slug,
        slug=target.terraform.stack_slug,
        module_kind="composite",
        description="rpi_kubernetes AQP stack (synthesised)",
        cloud_provider=target.cloud_provider,
        environment=target.environment,
        provider=TerraformProviderRef(kind=target.cloud_provider),
        backend=TerraformBackendRef(kind="local"),
    )
    add_spec(spec)
    return spec


def _run_local_stack_impl(
    task_id: str,
    *,
    action: str,
    spec_name: str | None = None,
) -> dict[str, Any]:
    """Underlying implementation, callable from tests without Celery binding."""
    target = _deployment_target(_LOCAL_TARGET_ID)
    spec_name = spec_name or target.terraform.stack_slug
    if action not in _LOCAL_ACTIONS:
        msg = f"unknown local stack action {action!r}; valid: {sorted(_LOCAL_ACTIONS)}"
        emit_error(task_id, msg)
        return {"ok": False, "error": msg}

    emit(task_id, "load", f"loading {spec_name}", spec=spec_name, action=action)
    try:
        spec = _load_local_spec()
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"spec load failed: {exc}")
        return {"ok": False, "error": str(exc)}

    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=target.terraform.stack_slug,
        task_id=task_id,
        prerendered_workspace_dir=_resolve_local_env_path(),
    )

    try:
        if action in ("up", "apply", "build"):
            emit(task_id, "plan", "running terraform plan")
            plan_res = runtime.plan()
            if int(plan_res.exit_code or 0) not in (0, 2):
                payload = plan_res.to_dict()
                payload["ok"] = False
                emit_error(task_id, f"plan failed: {plan_res.error}")
                return payload
            emit(task_id, "apply", "running terraform apply")
            apply_res = runtime.apply(plan_file=None)
            payload = apply_res.to_dict()
            payload["ok"] = int(apply_res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
        if action in ("down", "destroy"):
            emit(task_id, "destroy", "running terraform destroy")
            res = runtime.destroy()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
        if action == "plan":
            res = runtime.plan()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) in (0, 2)
            emit_done(task_id, payload)
            return payload
        if action == "refresh":
            res = runtime.refresh()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_local_stack(%s) crashed", action)
        emit_error(task_id, str(exc))
        return {"ok": False, "error": str(exc)}

    msg = f"unhandled local stack action {action!r}"
    emit_error(task_id, msg)
    return {"ok": False, "error": msg}


def _run_rpi_stack_impl(
    task_id: str,
    *,
    action: str,
    spec_name: str | None = None,
) -> dict[str, Any]:
    """Underlying implementation for rpi stack actions."""
    target = _deployment_target(_RPI_TARGET_ID)
    spec_name = spec_name or target.terraform.stack_slug
    if action not in _LOCAL_ACTIONS:
        msg = f"unknown rpi stack action {action!r}; valid: {sorted(_LOCAL_ACTIONS)}"
        emit_error(task_id, msg)
        return {"ok": False, "error": msg}

    emit(task_id, "load", f"loading {spec_name}", spec=spec_name, action=action)
    try:
        spec = _load_rpi_spec()
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"spec load failed: {exc}")
        return {"ok": False, "error": str(exc)}

    from aqp.terraform.runtime import TerraformRuntime

    runtime = TerraformRuntime(
        spec=spec,
        workspace_id=target.terraform.stack_slug,
        task_id=task_id,
        prerendered_workspace_dir=_resolve_rpi_env_path(),
    )

    try:
        if action in ("up", "apply", "build"):
            emit(task_id, "plan", "running terraform plan")
            plan_res = runtime.plan()
            if int(plan_res.exit_code or 0) not in (0, 2):
                payload = plan_res.to_dict()
                payload["ok"] = False
                emit_error(task_id, f"plan failed: {plan_res.error}")
                return payload
            emit(task_id, "apply", "running terraform apply")
            apply_res = runtime.apply(plan_file=None)
            payload = apply_res.to_dict()
            payload["ok"] = int(apply_res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
        if action in ("down", "destroy"):
            emit(task_id, "destroy", "running terraform destroy")
            res = runtime.destroy()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
        if action == "plan":
            res = runtime.plan()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) in (0, 2)
            emit_done(task_id, payload)
            return payload
        if action == "refresh":
            res = runtime.refresh()
            payload = res.to_dict()
            payload["ok"] = int(res.exit_code or 0) == 0
            emit_done(task_id, payload)
            return payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_rpi_stack(%s) crashed", action)
        emit_error(task_id, str(exc))
        return {"ok": False, "error": str(exc)}

    msg = f"unhandled rpi stack action {action!r}"
    emit_error(task_id, msg)
    return {"ok": False, "error": msg}


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_local_stack")
def run_local_stack(
    self,
    *,
    action: str,
    spec_name: str | None = None,
) -> dict[str, Any]:
    """Drive the local AQP stack through TerraformRuntime.

    Three-line shim around :func:`_run_local_stack_impl` so unit tests
    can call the body without monkeypatching the ``bind=True`` descriptor.
    """
    target = _deployment_target(_LOCAL_TARGET_ID)
    task_id = self.request.id or f"local:{action}"
    spec_name = spec_name or target.terraform.stack_slug
    return _run_local_stack_impl(task_id, action=action, spec_name=spec_name)


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.terraform_tasks.run_rpi_stack")
def run_rpi_stack(
    self,
    *,
    action: str,
    spec_name: str | None = None,
) -> dict[str, Any]:
    """Drive the rpi_kubernetes AQP stack through TerraformRuntime."""
    target = _deployment_target(_RPI_TARGET_ID)
    task_id = self.request.id or f"rpi:{action}"
    spec_name = spec_name or target.terraform.stack_slug
    return _run_rpi_stack_impl(task_id, action=action, spec_name=spec_name)


__all__ = [
    "_run_local_stack_impl",
    "_run_rpi_stack_impl",
    "cancel_terraform_run",
    "run_local_stack",
    "run_rpi_stack",
    "run_terraform_apply",
    "run_terraform_destroy",
    "run_terraform_plan",
    "run_terraform_refresh",
    "terraform_drift_scan",
]
