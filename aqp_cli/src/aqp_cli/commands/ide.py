"""``aqp-cli ide`` — the single canonical entrypoint for the AQP Theia IDE.

Lifecycle commands:

- ``install`` — yarn install inside ``aqp_ide/`` (one-time bootstrap)
- ``build``   — yarn build:extensions + build:applications[:dev]
- ``start``   — yarn .../applications/browser start (foreground or background)
- ``stop``    — kill the backgrounded Theia process
- ``status``  — show running pid, log path, configured port
- ``logs``    — tail the Theia log file
- ``open``    — open the Theia URL in the default browser
- ``url``     — print the Theia URL (local from state OR cluster topology)
- ``env``     — render / write the recommended AQP_THEIA_* env vars
- ``detect``  — surface every reachable Theia instance (local + cluster)
- ``doctor``  — preflight checks (yarn, port, MCP URLs, Auth0 token)

All commands honour AQP rule ``aqp-cli.mdc``: HTTP-only, no `aqp.*` /
`aqp_control_plane.*` imports, identity through ``IdentityProvider``,
tokens redacted to a 4-char prefix.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

import typer

from aqp_cli.clients.control_plane import ControlPlaneClient
from aqp_cli.clients.direct import DirectProbe
from aqp_cli.config import (
    AqpCliSettings,
    get_settings,
    ide_log_path,
    ide_state_path,
    resolve_access_token,
    resolve_repo_root,
)
from aqp_cli.process_manager import (
    is_pid_running,
    read_state,
    start_background_process,
    stop_background_process,
    tail_file,
)
from aqp_cli.ui.output import error, info, render_json, render_table, warn

app = typer.Typer(no_args_is_help=True, help="Control the AQP Theia IDE.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yarn() -> str:
    binary = shutil.which("yarn") or shutil.which("yarn.cmd")
    if not binary:
        error("yarn not on PATH")
        raise typer.Exit(code=127)
    return binary


def _ide_dir(settings: AqpCliSettings) -> Path:
    return resolve_repo_root(settings) / "aqp_ide"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _local_url(settings: AqpCliSettings, port: int | None = None) -> str:
    chosen_port = port or settings.theia_port
    base = settings.theia_url.rstrip("/")
    if base.endswith(f":{chosen_port}"):
        return base
    if "://localhost" in base and chosen_port == settings.theia_port:
        return base
    return f"http://localhost:{chosen_port}"


def _cluster_theia_url(settings: AqpCliSettings) -> str | None:
    """Return a Theia URL discovered via the control plane topology service."""
    token = resolve_access_token(settings)
    if not token:
        return None
    client = ControlPlaneClient(
        base_url=settings.control_plane_url,
        timeout=settings.http_timeout_seconds,
        access_token=token,
    )
    try:
        services = client.list_topology_services()
    except Exception:
        return None
    finally:
        client.close()
    for svc in services:
        name = str(svc.get("name") or "").lower()
        if name not in {"aqp-ide", "theia-ide"}:
            continue
        endpoints = svc.get("endpoints") or []
        if isinstance(endpoints, list):
            for ep in endpoints:
                if isinstance(ep, dict):
                    url = ep.get("url") or ep.get("href")
                    if isinstance(url, str) and url:
                        return url
        url = svc.get("url") or svc.get("href")
        if isinstance(url, str) and url:
            return url
    return None


# ---------------------------------------------------------------------------
# install / build
# ---------------------------------------------------------------------------


@app.command("install")
def install(
    frozen: bool = typer.Option(
        False,
        "--frozen-lockfile/--no-frozen-lockfile",
        help="Force the lockfile to be authoritative (reproducible builds).",
    ),
) -> None:
    """Run ``yarn install`` inside ``aqp_ide/`` (one-time bootstrap)."""
    settings = get_settings()
    yarn = _yarn()
    args = [yarn, "install"]
    if frozen or settings.theia_yarn_offline:
        args.append("--frozen-lockfile")
    info(f"running {' '.join(args)} in {_ide_dir(settings)}")
    rc = subprocess.run(args, cwd=str(_ide_dir(settings)), check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc))


@app.command("build")
def build(dev: bool = typer.Option(True, "--dev/--prod")) -> None:
    """Run ``yarn build:extensions`` then ``build:applications[:dev]``."""
    settings = get_settings()
    yarn = _yarn()
    ide_dir = _ide_dir(settings)
    rc = subprocess.run(  # noqa: S603
        [yarn, "build:extensions"],
        cwd=str(ide_dir),
        check=False,
    ).returncode
    if rc != 0:
        raise typer.Exit(code=int(rc))
    app_cmd = "build:applications:dev" if dev else "build:applications"
    rc2 = subprocess.run([yarn, app_cmd], cwd=str(ide_dir), check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc2))


# ---------------------------------------------------------------------------
# start / stop / status / logs
# ---------------------------------------------------------------------------


@app.command("start")
def start(
    background: bool = typer.Option(True, "--background/--foreground"),
    port: int = typer.Option(
        0,
        "--port",
        help="Override the configured Theia port. Persisted to the state file.",
    ),
    workspace: str = typer.Option(
        "",
        "--workspace",
        help="Workspace path passed positionally to `yarn start`.",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the IDE URL in the default browser once the server is ready.",
    ),
) -> None:
    """Start the local Theia IDE."""
    settings = get_settings()
    yarn = _yarn()
    state_file = ide_state_path(settings)
    log_file = ide_log_path(settings)

    chosen_port = port if port > 0 else settings.theia_port
    chosen_workspace = workspace or settings.theia_workspace

    current = read_state(state_file)
    current_pid = int(current.get("pid") or 0)
    if current_pid and is_pid_running(current_pid):
        render_json({
            "status": "already_running",
            "pid": current_pid,
            "state_file": str(state_file),
            "port": int(current.get("port") or chosen_port),
            "url": _local_url(settings, port=int(current.get("port") or chosen_port)),
        })
        if open_browser:
            webbrowser.open(_local_url(settings, port=int(current.get("port") or chosen_port)))
        return

    if _port_in_use(chosen_port):
        error(f"port {chosen_port} is in use; pick another with --port")
        raise typer.Exit(code=1)

    command: list[str] = [
        yarn,
        "--cwd",
        str(_ide_dir(settings) / "applications" / "browser"),
        "start",
    ]
    # Theia's `yarn start` honours `--port` as a forwarded arg.
    command.extend(["--", f"--port={chosen_port}", "--hostname=0.0.0.0"])
    if chosen_workspace:
        command.append(chosen_workspace)

    if not background:
        rc = subprocess.run(command, check=False).returncode  # noqa: S603
        raise typer.Exit(code=int(rc))

    metadata = start_background_process(
        state_file=state_file,
        log_file=log_file,
        command=command,
        cwd=_ide_dir(settings),
    )
    metadata["port"] = chosen_port
    metadata["url"] = _local_url(settings, port=chosen_port)
    # Re-write state file with the resolved port so `status` / `open` /
    # `url` can read it back without remembering the operator's flag.
    from aqp_cli.process_manager import write_state

    write_state(state_file, metadata)
    render_json({"status": "started", **metadata})
    if open_browser:
        # Best-effort wait for the Theia HTTP server to bind before opening.
        for _ in range(40):
            if _port_in_use(chosen_port):
                break
            time.sleep(0.25)
        webbrowser.open(metadata["url"])


@app.command("stop")
def stop() -> None:
    """Stop the local Theia IDE."""
    settings = get_settings()
    result = stop_background_process(ide_state_path(settings))
    render_json(result)


@app.command("status")
def status() -> None:
    """Show running pid, log path, configured port, and URL."""
    settings = get_settings()
    state = read_state(ide_state_path(settings))
    pid = int(state.get("pid") or 0)
    port = int(state.get("port") or settings.theia_port)
    out = dict(state)
    out["running"] = bool(pid and is_pid_running(pid))
    out["log_file"] = str(ide_log_path(settings))
    out["port"] = port
    out["url"] = _local_url(settings, port=port)
    render_json(out)


@app.command("logs")
def logs(lines: int = typer.Option(200, "--lines")) -> None:
    """Tail the Theia log file."""
    settings = get_settings()
    info(f"showing last {lines} lines from {ide_log_path(settings)}")
    typer.echo(tail_file(ide_log_path(settings), lines=lines))


# ---------------------------------------------------------------------------
# open / url
# ---------------------------------------------------------------------------


@app.command("open")
def open_browser(
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Print the URL instead of launching the default browser.",
    ),
) -> None:
    """Open the local Theia IDE URL in the default browser."""
    settings = get_settings()
    state = read_state(ide_state_path(settings))
    port = int(state.get("port") or settings.theia_port)
    url = state.get("url") or _local_url(settings, port=port)
    if no_browser:
        typer.echo(url)
        return
    info(f"opening {url}")
    webbrowser.open(str(url))


@app.command("url")
def url(remote: bool = typer.Option(False, "--remote", help="Show the cluster Theia URL via topology.")) -> None:
    """Print the Theia IDE URL.

    Default = local (from state file or settings). With ``--remote`` we
    query ``GET /manage/topology/services`` for a service named
    ``aqp-ide`` (or legacy ``theia-ide``) and print its URL.
    """
    settings = get_settings()
    if remote:
        remote_url = _cluster_theia_url(settings)
        if not remote_url:
            error("no remote Theia URL found in the control plane topology")
            raise typer.Exit(code=1)
        typer.echo(remote_url)
        return
    state = read_state(ide_state_path(settings))
    port = int(state.get("port") or settings.theia_port)
    typer.echo(state.get("url") or _local_url(settings, port=port))


# ---------------------------------------------------------------------------
# env / detect / doctor
# ---------------------------------------------------------------------------


_THEIA_ENV_KEYS = (
    "AQP_THEIA_AUTH0_DOMAIN",
    "AQP_THEIA_AUTH0_CLIENT_ID",
    "AQP_THEIA_AUTH0_AUDIENCE",
    "AQP_THEIA_AUTH0_SCOPE",
    "AQP_THEIA_AUTH0_REDIRECT_URI",
    "AQP_THEIA_AUTH0_ORGANIZATION",
    "AQP_THEIA_AUTH0_PUBLIC_ORIGIN",
    "AQP_THEIA_API_URL",
    "AQP_THEIA_FRONTEND_URL",
    "AQP_THEIA_PROVIDERS_URL",
    "AQP_THEIA_PUBLIC_ORIGIN",
    "AQP_THEIA_MCP_DATA_URL",
    "AQP_THEIA_MCP_DATA_AUDIENCE",
    "AQP_THEIA_MCP_CODEBASE_URL",
    "AQP_THEIA_MCP_CODEBASE_AUDIENCE",
    "AQP_THEIA_SERA_ENABLED",
    "AQP_THEIA_ROUTER_COMPLETE_PATH",
)


@app.command("env")
def env(
    write: Path | None = typer.Option(
        None,
        "--write",
        help="Write the resolved env file to PATH (default: stdout-only).",
    ),
) -> None:
    """Render the recommended ``AQP_THEIA_*`` env block.

    Resolution order per key: existing ``os.environ`` -> /auth/config
    BFF -> the cluster topology snapshot -> empty (operator fills in).

    Never prints secret material (tokens / audiences are not secrets;
    PKCE makes the SPA client_id public — see browser.Dockerfile docs).
    """
    import os

    settings = get_settings()
    resolved: dict[str, str] = {}
    for key in _THEIA_ENV_KEYS:
        resolved[key] = os.environ.get(key, "")

    # Pull what we can from the control plane (best-effort).
    token = resolve_access_token(settings)
    if token:
        with contextlib.suppress(Exception):
            client = ControlPlaneClient(
                base_url=settings.control_plane_url,
                timeout=settings.http_timeout_seconds,
                access_token=token,
            )
            try:
                services = client.list_topology_services()
            finally:
                client.close()
            for svc in services:
                name = str(svc.get("name") or "").lower()
                if name in {"aqp-api", "aqp"}:
                    url = svc.get("url") or ""
                    if isinstance(url, str) and url and not resolved.get("AQP_THEIA_API_URL"):
                        resolved["AQP_THEIA_API_URL"] = url
                if name in {"aqp-client", "aqp-frontend", "aqp-vite"}:
                    url = svc.get("url") or ""
                    if isinstance(url, str) and url and not resolved.get("AQP_THEIA_FRONTEND_URL"):
                        resolved["AQP_THEIA_FRONTEND_URL"] = url
                if name in {"aqp-data-mcp", "data-mcp"}:
                    url = svc.get("url") or ""
                    if isinstance(url, str) and url and not resolved.get("AQP_THEIA_MCP_DATA_URL"):
                        resolved["AQP_THEIA_MCP_DATA_URL"] = url
                if name in {"aqp-codebase-mcp", "codebase-mcp"}:
                    url = svc.get("url") or ""
                    if isinstance(url, str) and url and not resolved.get("AQP_THEIA_MCP_CODEBASE_URL"):
                        resolved["AQP_THEIA_MCP_CODEBASE_URL"] = url
    body_lines = [f"{k}={v}" for k, v in resolved.items()]
    body = "\n".join(body_lines) + "\n"
    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(body, encoding="utf-8")
        info(f"wrote {len(_THEIA_ENV_KEYS)} env keys to {write}")
        return
    typer.echo(body)


@app.command("detect")
def detect() -> None:
    """Surface every reachable Theia instance — local + cluster."""
    settings = get_settings()
    rows: list[list[str]] = []

    local_state = read_state(ide_state_path(settings))
    local_pid = int(local_state.get("pid") or 0)
    if local_pid and is_pid_running(local_pid):
        rows.append([
            "local",
            "aqp-ide",
            str(local_state.get("port") or settings.theia_port),
            "running",
            str(local_state.get("url") or _local_url(settings)),
        ])
    else:
        probe = DirectProbe()
        for entry in probe.discover():
            if entry["name"] == "theia-ide":
                rows.append([
                    "local",
                    entry["name"],
                    str(entry["port"]),
                    entry["state"],
                    f"http://localhost:{entry['port']}" if entry["state"] == "running" else "-",
                ])

    remote_url = _cluster_theia_url(settings)
    if remote_url:
        rows.append([
            "cluster",
            "aqp-ide",
            "-",
            "running",
            remote_url,
        ])

    if not rows:
        warn("no Theia instances detected (local OR cluster)")
        return
    render_table(
        "Detected Theia instances",
        ["scope", "name", "port", "state", "url"],
        rows,
    )


@app.command("doctor")
def doctor() -> None:
    """Run preflight checks for the local AQP IDE setup."""
    settings = get_settings()
    rows: list[list[str]] = []

    yarn_path = shutil.which("yarn") or shutil.which("yarn.cmd") or ""
    rows.append(["yarn on PATH", "OK" if yarn_path else "MISSING", yarn_path or "install yarn 1.x"])

    ide_dir = _ide_dir(settings)
    rows.append([
        "aqp_ide/ exists",
        "OK" if ide_dir.exists() else "MISSING",
        str(ide_dir),
    ])

    pkg_json = ide_dir / "package.json"
    rows.append([
        "aqp_ide/package.json",
        "OK" if pkg_json.exists() else "MISSING",
        str(pkg_json),
    ])

    yarn_lock = ide_dir / "yarn.lock"
    rows.append([
        "aqp_ide/yarn.lock",
        "OK" if yarn_lock.exists() else "MISSING (run `aqp-cli ide install`)",
        str(yarn_lock),
    ])

    port_free = not _port_in_use(settings.theia_port)
    rows.append([
        f"port {settings.theia_port} free",
        "OK" if port_free else "IN USE",
        str(settings.theia_port),
    ])

    token = resolve_access_token(settings)
    rows.append([
        "auth token present",
        "OK" if token else "MISSING (run `aqp-cli auth login --device`)",
        "<keyring>" if token else "<none>",
    ])

    state = read_state(ide_state_path(settings))
    pid = int(state.get("pid") or 0)
    running = bool(pid and is_pid_running(pid))
    rows.append([
        "local Theia running",
        "OK" if running else "stopped",
        f"pid {pid}" if running else "-",
    ])

    render_table(
        "AQP IDE doctor",
        ["check", "result", "detail"],
        rows,
    )

    any_problem = any(row[1] not in {"OK", "stopped"} for row in rows)
    if any_problem:
        raise typer.Exit(code=1)


__all__ = ["app"]


def _module_smoke_test() -> dict[str, Any]:
    """Used by aqp_cli tests/test_cli_smoke.py to assert this module is importable."""
    return {"commands": [c.name for c in app.registered_commands]}
