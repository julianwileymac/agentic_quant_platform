"""`aqp-cli deploy` — local resource deployment helpers."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import httpx
import typer

from aqp_cli.commands._common import exit_for_http_error, monolith_client, settings_and_token
from aqp_cli.config import resolve_repo_root
from aqp_cli.ui.output import error, info, render_json

app = typer.Typer(
    name="deploy",
    help="Local stack lifecycle (Terraform/API + local build/log wrappers).",
    no_args_is_help=True,
)


def _run_subprocess(args: list[str], *, cwd: str = "") -> int:
    info("running: " + " ".join(args))
    completed = subprocess.run(args, cwd=cwd or None, check=False)  # noqa: S603
    return int(completed.returncode)


def _resolve_workspace(client: Any, explicit_workspace_id: str = "") -> dict[str, Any]:
    payload = client.request("GET", "/terraform/workspaces")
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data") or payload.get("workspaces") or []
    else:
        items = payload
    if not isinstance(items, list):
        raise RuntimeError("No terraform workspace list available")
    workspaces = [item for item in items if isinstance(item, dict)]
    if not workspaces:
        raise RuntimeError("No terraform workspaces found")
    if explicit_workspace_id:
        for workspace in workspaces:
            if workspace.get("id") == explicit_workspace_id:
                return workspace
        raise RuntimeError(f"Workspace {explicit_workspace_id!r} not found")
    for workspace in workspaces:
        slug = str(workspace.get("slug") or "")
        if "local" in slug:
            return workspace
    return workspaces[0]


def _run_id_from_stream(task_payload: Any) -> str:
    if not isinstance(task_payload, dict):
        return ""
    stream = str(task_payload.get("stream_url") or "")
    if "/ws/terraform/runs/" in stream:
        return stream.rsplit("/", 1)[-1]
    return ""


@app.command("plan")
def plan(workspace_id: str = typer.Option("", "--workspace-id")) -> None:
    client = monolith_client(require_token=True)
    try:
        workspace = _resolve_workspace(client, workspace_id)
        payload = client.request(
            "POST",
            f"/terraform/workspaces/{workspace['id']}/plan",
            json_body={"var_overrides": {}, "destroy_plan": False},
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(
        {
            "workspace_id": workspace.get("id"),
            "workspace_slug": workspace.get("slug"),
            "task": payload,
            "plan_run_id": _run_id_from_stream(payload),
        }
    )


@app.command("apply")
def apply(
    workspace_id: str = typer.Option("", "--workspace-id"),
    plan_run_id: str = typer.Option("", "--plan-run-id"),
    note: str = typer.Option("", "--note"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        workspace = _resolve_workspace(client, workspace_id)
        effective_plan_run_id = plan_run_id
        if not effective_plan_run_id:
            task = client.request(
                "POST",
                f"/terraform/workspaces/{workspace['id']}/plan",
                json_body={"var_overrides": {}, "destroy_plan": False},
            )
            effective_plan_run_id = _run_id_from_stream(task)
            if not effective_plan_run_id:
                raise RuntimeError("Unable to derive plan run id from stream_url.")
        body: dict[str, Any] = {"plan_run_id": effective_plan_run_id}
        if note:
            body["approver_note"] = note
        payload = client.request(
            "POST", f"/terraform/workspaces/{workspace['id']}/apply", json_body=body
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(
        {
            "workspace_id": workspace.get("id"),
            "workspace_slug": workspace.get("slug"),
            "apply_run_id": _run_id_from_stream(payload),
            "task": payload,
        }
    )


@app.command("up")
def up(workspace_id: str = typer.Option("", "--workspace-id")) -> None:
    """Alias to `deploy apply`."""
    apply(workspace_id=workspace_id, plan_run_id="", note="")


@app.command("down")
def down(
    workspace_id: str = typer.Option("", "--workspace-id"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    note: str = typer.Option("", "--note"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        workspace = _resolve_workspace(client, workspace_id)
        slug = str(workspace.get("slug") or "")
        if not yes and not typer.confirm(f"Destroy workspace {slug!r}?"):
            info("aborted")
            raise typer.Exit(code=0)
        body: dict[str, Any] = {"confirmation_phrase": slug}
        if note:
            body["approver_note"] = note
        payload = client.request(
            "POST", f"/terraform/workspaces/{workspace['id']}/destroy", json_body=body
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(
        {
            "workspace_id": workspace.get("id"),
            "workspace_slug": workspace.get("slug"),
            "destroy_run_id": _run_id_from_stream(payload),
            "task": payload,
        }
    )


@app.command("refresh")
def refresh(workspace_id: str = typer.Option("", "--workspace-id")) -> None:
    client = monolith_client(require_token=True)
    try:
        workspace = _resolve_workspace(client, workspace_id)
        payload = client.request(
            "POST", f"/terraform/workspaces/{workspace['id']}/refresh", json_body={}
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(payload)


@app.command("status")
def status() -> None:
    client = monolith_client(require_token=True)
    try:
        service_health = client.request("GET", "/service-manager/health")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(service_health)


@app.command("logs")
def logs(
    service: str = typer.Argument(..., help="Service name (api/worker/beat/minio/etc)."),
    lines: int = typer.Option(200, "--lines"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        payload = client.request("GET", f"/service-manager/{service}/logs", params={"lines": lines})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(payload)


@app.command("endpoints")
def endpoints() -> None:
    settings, token = settings_and_token()
    client = monolith_client(require_token=True)
    try:
        vis = client.request("GET", "/visualizations/config")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(
        {
            "api_url": settings.api_url,
            "control_plane_url": settings.control_plane_url,
            "has_token": bool(token),
            "visualization": vis,
        }
    )


@app.command("build")
def build(skip_frontend: bool = typer.Option(False, "--skip-frontend")) -> None:
    settings, _ = settings_and_token()
    repo_root = resolve_repo_root(settings)
    if not skip_frontend:
        pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
        if not pnpm:
            error("pnpm not on PATH")
            raise typer.Exit(code=127)
        rc = _run_subprocess([pnpm, "--dir", str(repo_root / "aqp_client"), "build"])
        if rc != 0:
            raise typer.Exit(code=rc)
    info("build completed")


@app.command("publish-rpi")
def publish_rpi(
    registry: str = typer.Option(..., "--registry"),
    tag: str = typer.Option(..., "--tag"),
    skip_frontend: bool = typer.Option(False, "--skip-frontend"),
) -> None:
    settings, _ = settings_and_token()
    repo_root = resolve_repo_root(settings)
    docker = shutil.which("docker")
    if docker is None:
        error("docker not on PATH")
        raise typer.Exit(code=127)

    if not skip_frontend:
        pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
        if not pnpm:
            error("pnpm not on PATH")
            raise typer.Exit(code=127)
        rc = _run_subprocess([pnpm, "--dir", str(repo_root / "aqp_client"), "build"])
        if rc != 0:
            raise typer.Exit(code=rc)

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
            cwd=str(repo_root),
        )
        if rc != 0:
            raise typer.Exit(code=rc)
        rc = _run_subprocess([docker, "push", image])
        if rc != 0:
            raise typer.Exit(code=rc)

    frontend_image = f"{registry}/aqp-frontend:{tag}"
    frontend_dockerfile = repo_root / "aqp_client" / "Dockerfile.tf"
    if not frontend_dockerfile.exists():
        frontend_dockerfile.write_text(
            "FROM nginx:1.27-alpine\n"
            "COPY aqp_client/dist/ /usr/share/nginx/html/\n"
            "RUN printf 'server {\\n  listen 80;\\n  root /usr/share/nginx/html;\\n  "
            "location / {\\n    try_files $$uri $$uri/ /index.html;\\n  }\\n}\\n' > "
            "/etc/nginx/conf.d/default.conf\n"
            "EXPOSE 80\n",
            encoding="utf-8",
        )
    rc = _run_subprocess(
        [docker, "build", "-t", frontend_image, "-f", str(frontend_dockerfile), str(repo_root)],
        cwd=str(repo_root),
    )
    if rc != 0:
        raise typer.Exit(code=rc)
    rc = _run_subprocess([docker, "push", frontend_image])
    if rc != 0:
        raise typer.Exit(code=rc)
    info(f"published rpi images with tag {tag}")
