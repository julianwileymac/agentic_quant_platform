"""`aqp-cli ide` — local Theia IDE controls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

from aqp_cli.config import get_settings, ide_log_path, ide_state_path, resolve_repo_root
from aqp_cli.process_manager import (
    is_pid_running,
    read_state,
    start_background_process,
    stop_background_process,
    tail_file,
)
from aqp_cli.ui.output import error, info, render_json

app = typer.Typer(no_args_is_help=True, help="Control local Theia IDE.")


def _yarn() -> str:
    binary = shutil.which("yarn") or shutil.which("yarn.cmd")
    if not binary:
        error("yarn not on PATH")
        raise typer.Exit(code=127)
    return binary


def _ide_dir() -> Path:
    settings = get_settings()
    return resolve_repo_root(settings) / "aqp_ide"


@app.command("build")
def build(dev: bool = typer.Option(True, "--dev/--prod")) -> None:
    yarn = _yarn()
    ide_dir = _ide_dir()
    scripts = [yarn, "build:extensions"]
    rc = subprocess.run(scripts, cwd=str(ide_dir), check=False).returncode  # noqa: S603
    if rc != 0:
        raise typer.Exit(code=int(rc))
    app_cmd = "build:applications:dev" if dev else "build:applications"
    rc2 = subprocess.run([yarn, app_cmd], cwd=str(ide_dir), check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc2))


@app.command("start")
def start(
    background: bool = typer.Option(True, "--background/--foreground"),
) -> None:
    settings = get_settings()
    yarn = _yarn()
    state_file = ide_state_path(settings)
    log_file = ide_log_path(settings)
    current = read_state(state_file)
    pid = int(current.get("pid") or 0)
    if pid and is_pid_running(pid):
        render_json({"status": "already_running", "pid": pid, "state_file": str(state_file)})
        return

    command = [yarn, "--cwd", str(_ide_dir() / "applications" / "browser"), "start"]
    if not background:
        rc = subprocess.run(command, check=False).returncode  # noqa: S603
        raise typer.Exit(code=int(rc))

    metadata = start_background_process(
        state_file=state_file,
        log_file=log_file,
        command=command,
        cwd=_ide_dir(),
    )
    render_json({"status": "started", **metadata})


@app.command("stop")
def stop() -> None:
    settings = get_settings()
    result = stop_background_process(ide_state_path(settings))
    render_json(result)


@app.command("status")
def status() -> None:
    settings = get_settings()
    state = read_state(ide_state_path(settings))
    pid = int(state.get("pid") or 0)
    state["running"] = bool(pid and is_pid_running(pid))
    state["log_file"] = str(ide_log_path(settings))
    render_json(state or {"running": False})


@app.command("logs")
def logs(lines: int = typer.Option(200, "--lines")) -> None:
    settings = get_settings()
    info(f"showing last {lines} lines from {ide_log_path(settings)}")
    typer.echo(tail_file(ide_log_path(settings), lines=lines))
