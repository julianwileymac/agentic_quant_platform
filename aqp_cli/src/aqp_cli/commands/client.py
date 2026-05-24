"""`aqp-cli client` — local aqp_client dev/build/run controls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

from aqp_cli.config import client_log_path, client_state_path, get_settings, resolve_repo_root
from aqp_cli.process_manager import (
    is_pid_running,
    read_state,
    start_background_process,
    stop_background_process,
    tail_file,
)
from aqp_cli.ui.output import error, info, render_json

app = typer.Typer(no_args_is_help=True, help="Control the local Vite client.")


def _pnpm() -> str:
    binary = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if not binary:
        error("pnpm not on PATH")
        raise typer.Exit(code=127)
    return binary


def _client_dir() -> Path:
    settings = get_settings()
    return resolve_repo_root(settings) / "aqp_client"


@app.command("start")
def start(
    background: bool = typer.Option(True, "--background/--foreground"),
) -> None:
    settings = get_settings()
    pnpm = _pnpm()
    state_file = client_state_path(settings)
    log_file = client_log_path(settings)
    current = read_state(state_file)
    pid = int(current.get("pid") or 0)
    if pid and is_pid_running(pid):
        render_json({"status": "already_running", "pid": pid, "state_file": str(state_file)})
        return

    command = [pnpm, "--dir", str(_client_dir()), "dev"]
    if not background:
        rc = subprocess.run(command, check=False).returncode  # noqa: S603
        raise typer.Exit(code=int(rc))

    metadata = start_background_process(
        state_file=state_file,
        log_file=log_file,
        command=command,
        cwd=_client_dir(),
    )
    render_json({"status": "started", **metadata})


@app.command("stop")
def stop() -> None:
    settings = get_settings()
    result = stop_background_process(client_state_path(settings))
    render_json(result)


@app.command("status")
def status() -> None:
    settings = get_settings()
    state = read_state(client_state_path(settings))
    pid = int(state.get("pid") or 0)
    state["running"] = bool(pid and is_pid_running(pid))
    state["log_file"] = str(client_log_path(settings))
    render_json(state or {"running": False})


@app.command("logs")
def logs(lines: int = typer.Option(200, "--lines")) -> None:
    settings = get_settings()
    info(f"showing last {lines} lines from {client_log_path(settings)}")
    typer.echo(tail_file(client_log_path(settings), lines=lines))


@app.command("build")
def build() -> None:
    command = [_pnpm(), "--dir", str(_client_dir()), "build"]
    rc = subprocess.run(command, check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc))


@app.command("typecheck")
def typecheck() -> None:
    command = [_pnpm(), "--dir", str(_client_dir()), "typecheck"]
    rc = subprocess.run(command, check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc))
