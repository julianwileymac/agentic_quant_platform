"""`aqp-cli setup` — bootstrap a fresh local AQP environment."""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import typer

from aqp_cli.config import get_settings, resolve_repo_root
from aqp_cli.ui.output import info, render_json, warn

app = typer.Typer(no_args_is_help=True, help="Bootstrap local AQP environment.")


@app.command("init")
def init(
    env_file: str = typer.Option(".env", "--env-file", help="Path to write derived .env."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing env file."),
) -> None:
    """Bootstrap a local AQP environment (derived .env, volumes, networks)."""
    settings = get_settings()
    output = Path(env_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        warn(f"{output} already exists; pass --overwrite to replace it.")
        raise typer.Exit(code=1)
    payload = {
        "AQP_API_URL": settings.api_url,
        "AQP_CONTROL_PLANE_URL": settings.control_plane_url,
        "AQP_CLIENT_URL": "http://localhost:3001",
        "AQP_THEIA_URL": "http://localhost:3000",
    }
    lines = [f"{key}={value}" for key, value in payload.items()]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if overwrite:
        warn("--overwrite specified; existing file would be replaced.")
    render_json({"status": "ok", "env_file": str(output), "values": payload})


@app.command("verify")
def verify() -> None:
    """Verify local prerequisites (Docker, kubectl, Python, ports)."""
    checks = {
        "python": shutil.which("python") or shutil.which("python.exe") or "",
        "pnpm": shutil.which("pnpm") or shutil.which("pnpm.cmd") or "",
        "yarn": shutil.which("yarn") or shutil.which("yarn.cmd") or "",
        "docker": shutil.which("docker") or "",
        "kubectl": shutil.which("kubectl") or "",
    }
    ports: dict[str, bool] = {}
    for name, port in [("api", 8000), ("control_plane", 9000), ("client", 3001), ("theia", 3000)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            ports[name] = sock.connect_ex(("127.0.0.1", port)) == 0
    render_json({"binaries": checks, "ports_open": ports})


@app.command("render-config")
def render_config(
    output: str = typer.Option("configs/local.generated.yaml", "--output", "-o"),
) -> None:
    """Render derived local configuration from the topology service."""
    settings = get_settings()
    payload = {
        "api_url": settings.api_url,
        "control_plane_url": settings.control_plane_url,
        "repo_root": str(resolve_repo_root(settings)),
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    info(f"rendered {target}")
