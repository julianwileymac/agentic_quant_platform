# ruff: noqa
# from __future__ import annotations

import typer

from ._shim import run_aqp_cli

app = typer.Typer(help="Legacy deploy shim forwarding to aqp-cli deploy.")


@app.callback(invoke_without_command=True, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def callback(ctx: typer.Context) -> None:
    """Forward legacy ``aqp deploy`` commands to ``aqp-cli deploy``."""
    raise typer.Exit(run_aqp_cli(["deploy", *list(ctx.args)]))


__all__ = ["app", "callback"]
# from __future__ import annotations

import typer

from ._shim import run_aqp_cli

app = typer.Typer(help="Legacy deploy shim forwarding to aqp-cli deploy.")


@app.callback(invoke_without_command=True, context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def callback(ctx: typer.Context) -> None:
    """Forward legacy ``aqp deploy`` commands to ``aqp-cli deploy``."""
    raise typer.Exit(run_aqp_cli(["deploy", *list(ctx.args)]))


__all__ = ["app", "callback"]
"""Compatibility shim for `aqp deploy` -> `aqp-cli deploy`."""

# from __future__ import annotations

import typer

from aqp.cli._shim import run_aqp_cli

app = typer.Typer(
    name="deploy",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    raise typer.Exit(code=run_aqp_cli(["deploy", *list(ctx.args)]))


__all__ = ["app", "callback"]
"""Compatibility shim for `aqp deploy` -> `aqp-cli deploy`."""
# from __future__ import annotations

import typer

from aqp.cli._shim import run_aqp_cli

app = typer.Typer(
    name="deploy",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    raise typer.Exit(code=run_aqp_cli(["deploy", *list(ctx.args)]))


__all__ = ["app", "callback"]
"""``aqp deploy`` — local stack lifecycle (Terraform + k3d).

Routes every state-mutating command through
:class:`aqp.terraform.runtime.TerraformRuntime` so each apply / destroy
lands in the ``terraform_runs`` ledger, emits canonical
:func:`aqp.tasks._progress.emit` frames, and is halt-able from the
global kill switch (rule 42).

Read-only sub-commands (``status`` / ``logs``) shell out to
``kubectl`` directly because they don't mutate state — wrapping them
in TerraformRuntime would create empty ledger rows for every UI
refresh.

Bootstrap chicken-and-egg: when Postgres is the very thing being
booted, ``TerraformRuntime`` already degrades to no-op DB writes.
Subsequent applies (after the cluster is up) DO write to the ledger.
"""
# from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer

from aqp.config import settings
from aqp.deployment.topology import DeploymentTarget, get_target

app = typer.Typer(
    name="deploy",
    help="Local stack lifecycle (Terraform + k3d). Replaces docker-compose up/down.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Resolve the repo root (the directory containing pyproject.toml)."""
    here = Path(__file__).resolve()
    # aqp/cli/deploy_cmd.py -> aqp/cli -> aqp -> repo_root
    return here.parent.parent.parent


def _local_target() -> DeploymentTarget:
    return get_target("local")


def _local_env_dir() -> Path:
    return _local_target().terraform.environment_path


def _ensure_terraform_binary() -> str:
    binary = settings.terraform_binary or "terraform"
    resolved = shutil.which(binary)
    if not resolved:
        typer.secho(
            f"[aqp deploy] terraform binary {binary!r} not found on PATH. "
            "Install Terraform >= 1.10 or set AQP_TERRAFORM_BINARY.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(127)
    return resolved


def _ensure_k3d_binary() -> str:
    binary = "k3d"
    resolved = shutil.which(binary)
    if not resolved:
        typer.secho(
            "[aqp deploy] k3d not on PATH. Install via "
            "'choco install k3d' (Windows), 'brew install k3d' (macOS), "
            "or 'curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(127)
    return resolved


def _load_local_spec() -> Any:
    """Hydrate the canonical local TerraformStackSpec from the registry.

    Falls back to constructing a minimal spec if the YAML auto-load
    didn't pick the file up (e.g. CWD-sensitive path resolution).
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

    try:
        target = _local_target()
        return get_terraform_spec(target.terraform.stack_slug)
    except KeyError:
        pass

    yaml_dir = _repo_root() / "configs" / "terraform"
    if yaml_dir.exists():
        reload_yaml_dir(yaml_dir)
        try:
            target = _local_target()
            return get_terraform_spec(target.terraform.stack_slug)
        except KeyError:
            pass

    # Final fallback — synthesise an in-code spec so the CLI is
    # usable on a partial install.
    target = _local_target()
    spec = TerraformStackSpec(
        name=target.terraform.stack_slug,
        slug=target.terraform.stack_slug,
        module_kind="composite",
        description="Local AQP stack (synthesised fallback)",
        cloud_provider=target.cloud_provider,
        environment=target.environment,
        provider=TerraformProviderRef(kind=target.cloud_provider),
        backend=TerraformBackendRef(kind="local"),
    )
    add_spec(spec)
    return spec


def _build_runtime(spec: Any) -> Any:
    """Construct a TerraformRuntime pointed at the local environment dir.

    The ``prerendered_workspace_dir`` opt-out makes the executor
    skip codegen so the hand-authored composition under
    aqp_platform/terraform/environments/local/ runs as-is.
    """
    from aqp.terraform.runtime import TerraformRuntime

    return TerraformRuntime(
        spec=spec,
        workspace_id=_local_target().terraform.stack_slug,
        prerendered_workspace_dir=str(_local_env_dir()),
    )


def _print_run_result(result: Any, *, label: str) -> None:
    status = getattr(result, "status", "unknown")
    duration = float(getattr(result, "duration_ms", 0.0) or 0.0)
    color = (
        typer.colors.GREEN
        if status in {"completed", "succeeded", "ok"}
        else typer.colors.RED
        if status in {"error", "failed"}
        else typer.colors.YELLOW
    )
    typer.secho(
        f"[aqp deploy] {label}: status={status} duration_ms={duration:.0f}",
        fg=color,
    )
    err = getattr(result, "error", None)
    if err:
        typer.secho(f"  error: {err}", fg=typer.colors.RED, err=True)
    plan = getattr(result, "plan_summary", None) or {}
    if plan:
        typer.echo(f"  plan summary: {json.dumps(plan, sort_keys=True)}")
    if getattr(result, "stdout_log_uri", None):
        typer.echo(f"  stdout log: {result.stdout_log_uri}")


def _run_subprocess(args: list[str], *, label: str) -> int:
    """Streamed subprocess wrapper used by status / logs."""
    typer.echo(f"[aqp deploy] {label}: {' '.join(args)}")
    try:
        completed = subprocess.run(args, check=False)
    except FileNotFoundError as exc:
        typer.secho(f"[aqp deploy] command missing: {exc}", fg=typer.colors.RED, err=True)
        return 127
    return int(completed.returncode)


def _read_terraform_outputs() -> dict[str, Any]:
    """Pull the local environment's outputs as a dict.

    Best-effort — when terraform isn't on PATH or apply hasn't run,
    returns ``{}`` so callers can degrade cleanly.
    """
    binary = shutil.which(settings.terraform_binary or "terraform")
    if not binary:
        return {}
    wd = _local_env_dir()
    if not wd.exists():
        return {}
    try:
        completed = subprocess.run(
            [binary, "output", "-json"],
            cwd=str(wd),
            check=False,
            capture_output=True,
            timeout=30,
        )
    except Exception:  # noqa: BLE001
        return {}
    if completed.returncode != 0 or not completed.stdout:
        return {}
    try:
        raw = json.loads(completed.stdout.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {key: entry.get("value") for key, entry in raw.items() if isinstance(entry, dict)}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("plan")
def plan(
    destroy: bool = typer.Option(
        False, "--destroy", help="Plan a destroy run instead of an apply."
    ),
) -> None:
    """Run ``terraform plan`` against the local environment."""
    _ensure_terraform_binary()
    spec = _load_local_spec()
    runtime = _build_runtime(spec)
    typer.echo(f"[aqp deploy] planning {spec.name} (destroy={destroy})")
    result = runtime.plan(destroy=destroy)
    _print_run_result(result, label="plan")
    if getattr(result, "exit_code", 0) not in (None, 0, 2):
        raise typer.Exit(int(result.exit_code or 1))


@app.command("apply")
def apply(
    skip_plan: bool = typer.Option(
        False,
        "--skip-plan",
        help="Skip the implicit plan step. Apply uses the existing tfplan.",
    ),
) -> None:
    """Run ``terraform apply`` (plan + apply by default)."""
    _ensure_terraform_binary()
    _ensure_k3d_binary()
    spec = _load_local_spec()
    runtime = _build_runtime(spec)
    if not skip_plan:
        plan_result = runtime.plan()
        _print_run_result(plan_result, label="plan")
        if int(plan_result.exit_code or 0) not in (0, 2):
            typer.secho("[aqp deploy] plan failed; aborting apply", fg=typer.colors.RED, err=True)
            raise typer.Exit(int(plan_result.exit_code or 1))
    apply_result = runtime.apply(plan_file=None)
    _print_run_result(apply_result, label="apply")
    if int(apply_result.exit_code or 0) != 0:
        raise typer.Exit(int(apply_result.exit_code or 1))
    _print_endpoints()


@app.command("up")
def up() -> None:
    """Bring the local stack up. Equivalent to 'aqp deploy apply'.

    Replaces ``docker compose up -d`` as the canonical path.
    """
    apply()  # Re-use the apply pipeline; same ledger semantics.


@app.command("down")
def down(
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Run ``terraform destroy`` on the local stack."""
    _ensure_terraform_binary()
    if not yes:
        confirm = typer.confirm(
            "Tear down the entire local AQP stack (cluster + workloads)?",
            default=False,
        )
        if not confirm:
            typer.echo("[aqp deploy] aborted.")
            raise typer.Exit(0)
    spec = _load_local_spec()
    runtime = _build_runtime(spec)
    typer.echo(f"[aqp deploy] destroying {spec.name}")
    result = runtime.destroy()
    _print_run_result(result, label="destroy")
    if int(result.exit_code or 0) != 0:
        raise typer.Exit(int(result.exit_code or 1))


@app.command("build")
def build(
    skip_frontend: bool = typer.Option(
        False, "--skip-frontend", help="Skip 'pnpm --dir aqp_client build'."
    ),
) -> None:
    """Rebuild backend + frontend images and push them to the local registry.

    Re-runs only the ``module.aqp_images`` chain. Workloads pick up the
    new images on the next ``aqp deploy apply``.
    """
    _ensure_terraform_binary()
    repo_root = _repo_root()

    if not skip_frontend:
        pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
        if pnpm is None:
            typer.secho(
                "[aqp deploy] pnpm not on PATH; skipping frontend build. Install with "
                "'corepack enable && corepack prepare pnpm@latest --activate'.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        else:
            typer.echo("[aqp deploy] running 'pnpm --dir aqp_client build'")
            rc = _run_subprocess(
                [pnpm, "--dir", str(repo_root / "aqp_client"), "build"],
                label="frontend build",
            )
            if rc != 0:
                raise typer.Exit(rc)

    spec = _load_local_spec()
    runtime = _build_runtime(spec)
    # The aqp_images module is part of the same composition. Apply
    # the entire stack — Terraform's diffing keeps the run cheap when
    # only image triggers have changed.
    typer.echo(f"[aqp deploy] applying image-only changes for {spec.name}")
    plan_result = runtime.plan()
    _print_run_result(plan_result, label="build:plan")
    apply_result = runtime.apply(plan_file=None)
    _print_run_result(apply_result, label="build:apply")
    if int(apply_result.exit_code or 0) != 0:
        raise typer.Exit(int(apply_result.exit_code or 1))


@app.command("refresh")
def refresh() -> None:
    """Run ``terraform apply -refresh-only`` to sync state."""
    _ensure_terraform_binary()
    spec = _load_local_spec()
    runtime = _build_runtime(spec)
    result = runtime.refresh()
    _print_run_result(result, label="refresh")
    if int(result.exit_code or 0) != 0:
        raise typer.Exit(int(result.exit_code or 1))


@app.command("status")
def status(
    namespace: str | None = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Namespace to inspect. Defaults to the local target namespace from deployment topology.",
    ),
) -> None:
    """Read-only pod / service rollup. Shells out to ``kubectl``."""
    ns = namespace or _local_target().namespace
    kubectl = shutil.which("kubectl")
    if not kubectl:
        typer.secho(
            "[aqp deploy] kubectl not on PATH. Install via "
            "'choco install kubernetes-cli' or 'brew install kubectl'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(127)
    typer.echo("[aqp deploy] pods:")
    _run_subprocess([kubectl, "get", "pods", "-n", ns], label="kubectl get pods")
    typer.echo("[aqp deploy] services:")
    _run_subprocess([kubectl, "get", "svc", "-n", ns], label="kubectl get svc")
    _print_endpoints()


@app.command("logs")
def logs(
    service: str = typer.Argument(
        ...,
        help="Service name (api / worker / beat / frontend / postgres / redis / neo4j / chromadb / mlflow / jaeger / otel-collector).",
    ),
    namespace: str | None = typer.Option(
        None,
        "--namespace",
        "-n",
        help="Namespace to inspect. Defaults to the local target namespace from deployment topology.",
    ),
    follow: bool = typer.Option(
        True, "-f/--no-follow", help="Stream logs (default) or fetch a snapshot."
    ),
    tail: int = typer.Option(200, "--tail", help="Number of recent lines to fetch."),
) -> None:
    """Tail / dump pod logs by service label."""
    ns = namespace or _local_target().namespace
    kubectl = shutil.which("kubectl")
    if not kubectl:
        typer.secho("[aqp deploy] kubectl not on PATH.", fg=typer.colors.RED, err=True)
        raise typer.Exit(127)
    selector = f"app={service}" if not service.startswith("aqp-") else f"app={service}"
    args = [
        kubectl,
        "logs",
        "-n",
        ns,
        "-l",
        selector,
        f"--tail={tail}",
    ]
    if follow:
        args.append("-f")
    rc = _run_subprocess(args, label=f"kubectl logs {service}")
    if rc != 0:
        raise typer.Exit(rc)


@app.command("endpoints")
def endpoints() -> None:
    """Print the local stack's URL endpoints (api / frontend / mlflow / jaeger)."""
    _print_endpoints()


@app.command("publish-rpi")
def publish_rpi(
    registry: str = typer.Option(
        ..., "--registry", help="Registry reachable by rpi nodes, e.g. docker.io/<user>"
    ),
    tag: str = typer.Option(
        ..., "--tag", help="Immutable image tag to publish, e.g. 2026-05-18-sha"
    ),
    skip_frontend: bool = typer.Option(False, "--skip-frontend", help="Skip pnpm frontend build."),
) -> None:
    """Build and push immutable AQP images for the rpi_kubernetes target."""
    repo_root = _repo_root()
    docker = shutil.which("docker")
    if docker is None:
        typer.secho("[aqp deploy] docker not on PATH", fg=typer.colors.RED, err=True)
        raise typer.Exit(127)
    if not skip_frontend:
        pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
        if pnpm is None:
            typer.secho("[aqp deploy] pnpm not on PATH", fg=typer.colors.RED, err=True)
            raise typer.Exit(127)
        rc = _run_subprocess(
            [pnpm, "--dir", str(repo_root / "aqp_client"), "build"], label="frontend build"
        )
        if rc != 0:
            raise typer.Exit(rc)

    images = {
        "api": "api",
        "worker": "api",
        "beat": "api",
        "paper": "paper",
        "serving": "serving",
        "ingester": "ingester",
    }
    for name, target in images.items():
        image = f"{registry}/aqp-{name}:{tag}"
        rc = _run_subprocess(
            [docker, "build", "--target", target, "-t", image, "-f", "Dockerfile", "."],
            label=f"docker build {name}",
        )
        if rc != 0:
            raise typer.Exit(rc)
        rc = _run_subprocess([docker, "push", image], label=f"docker push {name}")
        if rc != 0:
            raise typer.Exit(rc)

    frontend_image = f"{registry}/aqp-frontend:{tag}"
    frontend_dockerfile = repo_root / "aqp_client" / "Dockerfile.tf"
    if not frontend_dockerfile.exists():
        frontend_dockerfile.write_text(
            "FROM nginx:1.27-alpine\nCOPY aqp_client/dist/ /usr/share/nginx/html/\n"
            "RUN printf 'server {\\n  listen 80;\\n  root /usr/share/nginx/html;\\n  location / {\\n    try_files $$uri $$uri/ /index.html;\\n  }\\n}\\n' > /etc/nginx/conf.d/default.conf\n"
            "EXPOSE 80\n",
            encoding="utf-8",
        )
    rc = _run_subprocess(
        [docker, "build", "-t", frontend_image, "-f", str(frontend_dockerfile), str(repo_root)],
        label="docker build frontend",
    )
    if rc != 0:
        raise typer.Exit(rc)
    rc = _run_subprocess([docker, "push", frontend_image], label="docker push frontend")
    if rc != 0:
        raise typer.Exit(rc)
    typer.echo(f"[aqp deploy] published rpi images with tag {tag}")


def _print_endpoints() -> None:
    outputs = _read_terraform_outputs()
    if not outputs:
        typer.secho(
            "[aqp deploy] no terraform outputs available. Run 'aqp deploy up' first.",
            fg=typer.colors.YELLOW,
        )
        return
    typer.echo("[aqp deploy] endpoints:")
    for key in ("frontend_url", "api_url", "mlflow_url_in_cluster", "jaeger_url_in_cluster"):
        value = outputs.get(key)
        if value:
            typer.echo(f"  {key:32s} {value}")
    extra = outputs.get("endpoints") or {}
    if isinstance(extra, dict):
        for key in ("registry", "kubeconfig", "namespace", "cluster"):
            if key in extra:
                typer.echo(f"  {key:32s} {extra[key]}")


__all__ = ["app"]

# Final override: export the deprecation-forwarding shim.
app = typer.Typer(
    name="deploy",
    help="Legacy deploy shim forwarding to aqp-cli deploy.",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    """Forward legacy ``aqp deploy`` commands to ``aqp-cli deploy``."""
    raise typer.Exit(run_aqp_cli(["deploy", *list(ctx.args)]))


def main(argv: list[str]) -> int:
    """Forward argv to ``aqp-cli deploy`` for non-Typer call sites."""
    return run_aqp_cli(["deploy", *argv])


__all__ = ["app", "callback", "main", "run_aqp_cli"]
