"""``TerraformExecutor`` — subprocess wrapper around the ``terraform`` CLI.

AGENTS rule 42: nothing else in the codebase calls
``subprocess.run(["terraform", ...])`` directly — every IaC lifecycle
action goes through this module via
:class:`aqp.terraform.runtime.TerraformRuntime`.

The executor:

1. Writes the rendered ``main.tf`` (+ any extra files) into a
   per-workspace directory under
   :attr:`Settings.terraform_workspaces_dir`.
2. Runs ``terraform init`` (idempotent — the ``-upgrade=false`` flag
   keeps subsequent plans fast).
3. Runs the operation (``plan`` / ``apply`` / ``destroy`` /
   ``refresh`` / ``state pull``).
4. Captures stdout + stderr to a per-run log file and (when
   ``apply``/``destroy``) parses the structured ``tfplan.json`` via
   ``terraform show -json tfplan``.
5. Returns a :class:`TerraformExecutorResult` the runtime persists
   onto the matching :class:`TerraformRun` row.

The executor honours :attr:`Settings.terraform_parallelism` and
respects :attr:`Settings.terraform_plugin_cache_dir` so concurrent
runs share the provider download cache.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aqp.terraform.codegen import render_spec
from aqp.terraform.spec import TerraformStackSpec

logger = logging.getLogger(__name__)

_TRANSIENT_INIT_FAILURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"failed to install provider", re.IGNORECASE),
    re.compile(r"failed to query available provider packages", re.IGNORECASE),
    re.compile(r"registry\.terraform\.io", re.IGNORECASE),
    re.compile(r"releases\.hashicorp\.com", re.IGNORECASE),
    re.compile(r"context deadline exceeded", re.IGNORECASE),
    re.compile(r"tls handshake timeout", re.IGNORECASE),
    re.compile(r"i/o timeout", re.IGNORECASE),
    re.compile(r"connection reset", re.IGNORECASE),
    re.compile(r"forcibly closed", re.IGNORECASE),
    re.compile(r"wsarecv", re.IGNORECASE),
    re.compile(r"temporary failure in name resolution", re.IGNORECASE),
    re.compile(r"no such host", re.IGNORECASE),
)


@dataclass
class TerraformExecutorResult:
    """Outcome of one ``terraform <action>`` subprocess invocation."""

    action: str
    workspace_dir: str
    exit_code: int
    duration_ms: float
    stdout_log_path: str
    stderr_log_path: str
    plan_artifact_path: str | None = None
    plan_summary_path: str | None = None
    plan_summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_run_row_payload(self) -> dict[str, Any]:
        return {
            "exit_code": int(self.exit_code),
            "duration_ms": float(self.duration_ms),
            "plan_artifact_uri": (
                f"file://{self.plan_artifact_path}" if self.plan_artifact_path else None
            ),
            "stdout_log_uri": f"file://{self.stdout_log_path}",
            "stderr_log_uri": f"file://{self.stderr_log_path}",
            "plan_summary_json": dict(self.plan_summary),
            "error": self.error,
        }


class TerraformExecutorError(RuntimeError):
    """Raised for executor-level failures (binary missing, IO failure)."""


class TerraformExecutor:
    """Per-workspace ``terraform`` subprocess wrapper.

    Construct one executor per :class:`TerraformWorkspace`; reuse it
    across plan / apply / refresh cycles so ``terraform init`` only
    runs once per workspace lifetime.
    """

    def __init__(
        self,
        *,
        workspace_slug: str,
        spec: TerraformStackSpec,
        workspaces_dir: str | os.PathLike[str] | None = None,
        binary: str | None = None,
        parallelism: int | None = None,
        plugin_cache_dir: str | os.PathLike[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        prerendered_workspace_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.workspace_slug = workspace_slug
        self.spec = spec
        self._binary = binary
        self._parallelism = parallelism
        self._plugin_cache_dir = plugin_cache_dir
        self._workspaces_dir_override = (
            Path(workspaces_dir) if workspaces_dir else None
        )
        # When set, ``prepare()`` is a no-op and ``workspace_dir()``
        # returns this path. Used for hand-authored compositions
        # (terraform/environments/<env>/) that already ship a main.tf
        # — the local AQP stack is the canonical example. Falsy
        # values leave the codegen path intact.
        self._prerendered_workspace_dir = (
            Path(prerendered_workspace_dir) if prerendered_workspace_dir else None
        )
        self._env_overrides = dict(env_overrides or {})
        self._initialised = False

    # ------------------------------------------------------------------
    # Configuration accessors
    # ------------------------------------------------------------------

    def _settings(self) -> Any | None:
        try:
            from aqp.config import settings

            return settings
        except Exception:  # pragma: no cover
            return None

    def _binary_path(self) -> str:
        if self._binary:
            return self._binary
        s = self._settings()
        path = str(getattr(s, "terraform_binary", "terraform") or "terraform")
        return shutil.which(path) or path

    def _workspaces_dir(self) -> Path:
        if self._workspaces_dir_override is not None:
            return self._workspaces_dir_override
        s = self._settings()
        return Path(getattr(s, "terraform_workspaces_dir", "./data/terraform/workspaces"))

    def _plugin_cache_path(self) -> Path | None:
        if self._plugin_cache_dir is not None:
            return Path(self._plugin_cache_dir)
        s = self._settings()
        raw = str(getattr(s, "terraform_plugin_cache_dir", "") or "").strip()
        return Path(raw) if raw else None

    def _parallelism_arg(self) -> int:
        if self._parallelism is not None:
            return int(self._parallelism)
        s = self._settings()
        return int(getattr(s, "terraform_parallelism", 10) or 10)

    def _cli_config_file(self) -> Path | None:
        s = self._settings()
        raw = str(getattr(s, "terraform_cli_config_file", "") or "").strip()
        if not raw:
            return None
        return Path(raw).expanduser()

    def _init_retry_attempts(self) -> int:
        s = self._settings()
        try:
            value = int(getattr(s, "terraform_init_retry_attempts", 3) or 3)
        except Exception:
            value = 3
        return max(1, value)

    def _init_retry_backoff_seconds(self) -> float:
        s = self._settings()
        try:
            value = float(getattr(s, "terraform_init_retry_backoff_seconds", 2.0) or 2.0)
        except Exception:
            value = 2.0
        return max(0.0, value)

    def _init_retry_max_backoff_seconds(self) -> float:
        s = self._settings()
        try:
            value = float(
                getattr(s, "terraform_init_retry_max_backoff_seconds", 30.0) or 30.0
            )
        except Exception:
            value = 30.0
        return max(0.0, value)

    def workspace_dir(self) -> Path:
        if self._prerendered_workspace_dir is not None:
            return self._prerendered_workspace_dir
        return self._workspaces_dir() / self.workspace_slug

    # ------------------------------------------------------------------
    # Preparation
    # ------------------------------------------------------------------

    def prepare(self) -> Path:
        """Materialise the workspace directory + rendered ``main.tf``.

        Idempotent — repeated calls re-render the file so spec edits
        between plan / apply land cleanly. Returns the workspace
        :class:`pathlib.Path`.

        When ``prerendered_workspace_dir`` was passed to the
        constructor (the local AQP stack uses this) the method is a
        no-op: the directory already ships a hand-authored composition
        and the codegen template would clobber it.
        """
        if self._prerendered_workspace_dir is not None:
            wd = self._prerendered_workspace_dir
            if not wd.exists():
                raise TerraformExecutorError(
                    f"prerendered_workspace_dir {wd} does not exist"
                )
            return wd

        wd = self.workspace_dir()
        wd.mkdir(parents=True, exist_ok=True)
        # Drop a tagging README so operators inspecting the cache dir
        # know which logical stack produced the files.
        readme = wd / "AQP_README.md"
        if not readme.exists():
            readme.write_text(
                f"# AQP Terraform workspace\n\n"
                f"- slug: {self.workspace_slug}\n"
                f"- spec name: {self.spec.name}\n"
                f"- spec hash: {self.spec.snapshot_hash()}\n"
                f"- module_kind: {self.spec.module_kind}\n"
                f"- cloud_provider: {self.spec.cloud_provider}\n"
                f"- environment: {self.spec.environment}\n"
                f"\nManaged by aqp.terraform.runner — do not hand-edit main.tf.\n",
                encoding="utf-8",
            )
        main_tf = wd / "main.tf"
        rendered = render_spec(self.spec)
        main_tf.write_text(rendered, encoding="utf-8")
        return wd

    # ------------------------------------------------------------------
    # Subprocess driver
    # ------------------------------------------------------------------

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        cache = self._plugin_cache_path()
        if cache is not None:
            cache.mkdir(parents=True, exist_ok=True)
            env["TF_PLUGIN_CACHE_DIR"] = str(cache)
        cli_config = self._cli_config_file()
        if cli_config is not None:
            if cli_config.exists():
                env["TF_CLI_CONFIG_FILE"] = str(cli_config)
            else:
                logger.warning(
                    "terraform_cli_config_file %s does not exist; "
                    "ignoring TF_CLI_CONFIG_FILE override",
                    cli_config,
                )
        env["TF_IN_AUTOMATION"] = "true"
        env["TF_INPUT"] = "false"
        env["CHECKPOINT_DISABLE"] = "1"
        env.update(self._env_overrides)
        return env

    def _is_transient_init_failure(self, stderr_log_path: str) -> bool:
        try:
            text = Path(stderr_log_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False
        if not text.strip():
            return False
        return any(p.search(text) for p in _TRANSIENT_INIT_FAILURE_PATTERNS)

    def _init_retry_sleep_seconds(self, attempt_number: int) -> float:
        # attempt_number is 2-based (attempt 1 is the initial run).
        base = self._init_retry_backoff_seconds()
        cap = self._init_retry_max_backoff_seconds()
        if base <= 0:
            return 0.0
        exponent = max(0, attempt_number - 2)
        return min(cap, base * (2**exponent))

    def _run(
        self,
        args: list[str],
        *,
        action: str,
        timeout_seconds: int = 1800,
    ) -> TerraformExecutorResult:
        wd = self.prepare()
        binary = self._binary_path()
        if not binary:
            raise TerraformExecutorError(
                "terraform binary not found; install it or set AQP_TERRAFORM_BINARY"
            )

        stdout_path = wd / f"{action}.stdout.log"
        stderr_path = wd / f"{action}.stderr.log"
        plan_artifact: Path | None = None
        plan_summary_path: Path | None = None
        plan_summary: dict[str, Any] = {}

        started = time.time()
        try:
            with stdout_path.open("w", encoding="utf-8") as out_f, stderr_path.open(
                "w", encoding="utf-8"
            ) as err_f:
                completed = subprocess.run(  # noqa: S603 - args list, no shell
                    [binary, *args],
                    cwd=str(wd),
                    env=self._env(),
                    stdout=out_f,
                    stderr=err_f,
                    timeout=timeout_seconds,
                    check=False,
                )
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            elapsed = (time.time() - started) * 1000.0
            return TerraformExecutorResult(
                action=action,
                workspace_dir=str(wd),
                exit_code=124,
                duration_ms=elapsed,
                stdout_log_path=str(stdout_path),
                stderr_log_path=str(stderr_path),
                error=f"terraform {action} timed out after {timeout_seconds}s: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.time() - started) * 1000.0
            return TerraformExecutorResult(
                action=action,
                workspace_dir=str(wd),
                exit_code=1,
                duration_ms=elapsed,
                stdout_log_path=str(stdout_path),
                stderr_log_path=str(stderr_path),
                error=f"terraform {action} failed to start: {exc}",
            )

        elapsed_ms = (time.time() - started) * 1000.0

        # Plan post-processing: convert tfplan -> JSON summary.
        if action == "plan" and exit_code in (0, 2):
            # exit_code 0 = no changes, 2 = changes detected (per
            # terraform plan -detailed-exitcode convention).
            plan_artifact = wd / "tfplan"
            if plan_artifact.exists():
                plan_summary_path = wd / "tfplan.json"
                try:
                    completed_show = subprocess.run(  # noqa: S603
                        [binary, "show", "-json", "tfplan"],
                        cwd=str(wd),
                        env=self._env(),
                        capture_output=True,
                        timeout=300,
                        check=False,
                    )
                    if completed_show.returncode == 0 and completed_show.stdout:
                        plan_summary_path.write_bytes(completed_show.stdout)
                        try:
                            plan_summary = _summarize_plan(
                                json.loads(completed_show.stdout)
                            )
                        except Exception:
                            plan_summary = {}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("terraform show -json failed: %s", exc)

        return TerraformExecutorResult(
            action=action,
            workspace_dir=str(wd),
            exit_code=exit_code,
            duration_ms=elapsed_ms,
            stdout_log_path=str(stdout_path),
            stderr_log_path=str(stderr_path),
            plan_artifact_path=str(plan_artifact) if plan_artifact else None,
            plan_summary_path=str(plan_summary_path) if plan_summary_path else None,
            plan_summary=plan_summary,
            error=None,
        )

    def outputs_json(self, *, timeout_seconds: int = 30) -> dict[str, Any]:
        """Return ``terraform output -json`` values for this workspace.

        This is intentionally read-only but still lives inside the executor so
        API/route code never shells out to Terraform directly.
        """
        wd = self.prepare()
        binary = self._binary_path()
        if not binary:
            raise TerraformExecutorError(
                "terraform binary not found; install it or set AQP_TERRAFORM_BINARY"
            )
        completed = subprocess.run(  # noqa: S603 - args list, no shell
            [binary, "output", "-json"],
            cwd=str(wd),
            env=self._env(),
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
        if completed.returncode != 0 or not completed.stdout:
            return {}
        raw = json.loads(completed.stdout.decode("utf-8"))
        return {
            key: entry.get("value")
            for key, entry in raw.items()
            if isinstance(entry, dict)
        }

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def init(self, *, upgrade: bool = False) -> TerraformExecutorResult:
        args = ["init", "-input=false"]
        if not upgrade:
            args.append("-upgrade=false")
        attempts = self._init_retry_attempts()
        attempt = 1
        result = self._run(args, action="init", timeout_seconds=900)
        while attempt < attempts and result.exit_code != 0:
            if not self._is_transient_init_failure(result.stderr_log_path):
                break
            attempt += 1
            sleep_seconds = self._init_retry_sleep_seconds(attempt)
            logger.warning(
                "terraform init failed for workspace=%s (attempt %s/%s, exit=%s); "
                "retrying in %.1fs",
                self.workspace_slug,
                attempt - 1,
                attempts,
                result.exit_code,
                sleep_seconds,
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            result = self._run(args, action="init", timeout_seconds=900)

        if result.exit_code == 0:
            self._initialised = True
            return result
        if result.error is None:
            if attempt > 1:
                result.error = (
                    f"terraform init failed after {attempt} attempts; "
                    f"see stderr log at {result.stderr_log_path}"
                )
            else:
                result.error = (
                    f"terraform init failed; see stderr log at {result.stderr_log_path}"
                )
        return result

    def plan(
        self,
        *,
        destroy: bool = False,
        var_overrides: dict[str, str] | None = None,
    ) -> TerraformExecutorResult:
        if not self._initialised:
            init_result = self.init()
            if init_result.exit_code != 0:
                return init_result
        args = [
            "plan",
            "-input=false",
            f"-parallelism={self._parallelism_arg()}",
            "-detailed-exitcode",
            "-out=tfplan",
        ]
        if destroy:
            args.append("-destroy")
        for k, v in (var_overrides or {}).items():
            args.extend(["-var", f"{k}={v}"])
        return self._run(args, action="plan", timeout_seconds=1800)

    def apply(
        self,
        *,
        plan_file: str | None = "tfplan",
    ) -> TerraformExecutorResult:
        if not self._initialised:
            init_result = self.init()
            if init_result.exit_code != 0:
                return init_result
        args = [
            "apply",
            "-input=false",
            "-auto-approve",
            f"-parallelism={self._parallelism_arg()}",
        ]
        if plan_file:
            args.append(plan_file)
        return self._run(args, action="apply", timeout_seconds=3600)

    def destroy(self) -> TerraformExecutorResult:
        if not self._initialised:
            init_result = self.init()
            if init_result.exit_code != 0:
                return init_result
        args = [
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-parallelism={self._parallelism_arg()}",
        ]
        return self._run(args, action="destroy", timeout_seconds=3600)

    def refresh(self) -> TerraformExecutorResult:
        if not self._initialised:
            init_result = self.init()
            if init_result.exit_code != 0:
                return init_result
        args = ["apply", "-refresh-only", "-auto-approve", "-input=false"]
        return self._run(args, action="refresh", timeout_seconds=1800)

    def state_pull(self) -> TerraformExecutorResult:
        return self._run(["state", "pull"], action="state_pull", timeout_seconds=300)

    def validate(self) -> TerraformExecutorResult:
        return self._run(["validate"], action="validate", timeout_seconds=300)

    def unlock(self, lock_id: str) -> TerraformExecutorResult:
        return self._run(
            ["force-unlock", "-force", lock_id],
            action="unlock",
            timeout_seconds=120,
        )


# ---------------------------------------------------------------------------
# Plan summarization
# ---------------------------------------------------------------------------


def _summarize_plan(plan_json: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full ``terraform show -json`` payload to a UI-friendly summary."""
    changes = plan_json.get("resource_changes") or []
    add = update = destroy = recreate = read = no_op = 0
    grouped: dict[str, int] = {}
    for entry in changes:
        actions = (entry.get("change") or {}).get("actions") or []
        kind = "no-op"
        if actions == ["create"]:
            add += 1
            kind = "create"
        elif actions == ["update"]:
            update += 1
            kind = "update"
        elif actions == ["delete"]:
            destroy += 1
            kind = "delete"
        elif set(actions) == {"delete", "create"}:
            recreate += 1
            kind = "recreate"
        elif "read" in actions:
            read += 1
            kind = "read"
        else:
            no_op += 1
        grouped[kind] = grouped.get(kind, 0) + 1
    return {
        "create": add,
        "update": update,
        "destroy": destroy,
        "recreate": recreate,
        "read": read,
        "no_op": no_op,
        "total_changes": add + update + destroy + recreate,
        "by_kind": grouped,
        "format_version": plan_json.get("format_version"),
        "terraform_version": plan_json.get("terraform_version"),
    }


__all__ = [
    "TerraformExecutor",
    "TerraformExecutorError",
    "TerraformExecutorResult",
]
